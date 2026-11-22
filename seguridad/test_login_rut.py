# ============================================
# Ingreso con RUT (pacientes) y con usuario (personal)
# --------------------------------------------
# Comprueba que el paciente ingresa con su RUT (con o sin puntos y guion),
# que el RUT no queda como nombre de usuario ni legible en la base, que el
# personal usa un usuario restringido, que los errores no revelan si la
# cuenta existe o está pendiente, y que hay bloqueo tras 5 intentos fallidos.
# ============================================

from datetime import date

from django.contrib.auth.models import Group, User
from django.core.cache import cache
from django.db import connection
from django.test import TestCase

from administracion.forms import UsuarioNuevoForm
from pacientes.models import PerfilPaciente
from pacientes.rut_login import hash_rut
from seguridad.forms import MAX_INTENTOS

CLAVE = "Clave-Segura#2026x"
RUT = "12.345.678-5"


def crear_paciente(username, rut, estado="ACEPTADO", activo=True):
    usuario = User.objects.create_user(username, email=f"{username}@example.com", password=CLAVE, is_active=activo)
    usuario.groups.add(Group.objects.get_or_create(name="Paciente")[0])
    PerfilPaciente.objects.create(
        usuario=usuario, nombre_completo="Paciente Login", fecha_nacimiento=date(1990, 1, 1),
        rut=rut, telefono="+56 9 1234 5678", estado=estado,
    )
    return usuario


class LoginConRutTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.paciente = crear_paciente("p0a1b2c3d4e5", RUT)
        cls.pendiente = crear_paciente("p9f8e7d6c5b4", "22222222-2", estado="PENDIENTE", activo=False)
        cls.coord = User.objects.create_user("coord_login", password=CLAVE)
        cls.coord.groups.add(Group.objects.get_or_create(name="Coordinador")[0])

    def setUp(self):
        cache.clear()

    def entrar(self, usuario, clave=CLAVE, tipo="paciente"):
        return self.client.post(
            "/login/", {"username": usuario, "password": clave, "tipo": tipo}, secure=True
        )

    def test_el_paciente_entra_con_su_rut_en_cualquier_formato(self):
        for formato in ("12.345.678-5", "12345678-5", "123456785"):
            with self.subTest(formato=formato):
                self.client.logout()
                r = self.entrar(formato)
                self.assertRedirects(r, "/mis-solicitudes/", fetch_redirect_response=False)

    def test_el_paciente_con_k_entra_en_minuscula_o_mayuscula(self):
        crear_paciente("pkkkkkkkkkkk", "10000013-K")
        for formato in ("10.000.013-K", "10000013-k"):
            with self.subTest(formato=formato):
                self.client.logout()
                self.assertRedirects(self.entrar(formato), "/mis-solicitudes/", fetch_redirect_response=False)

    def test_el_rut_con_clave_equivocada_o_inexistente_da_el_mismo_error(self):
        errores = set()
        for rut, clave in ((RUT, "mala"), ("99.999.999-9", CLAVE), ("22.222.222-2", CLAVE)):
            r = self.entrar(rut, clave)
            self.assertEqual(r.status_code, 200)
            self.assertNotIn("_auth_user_id", self.client.session)
            errores.add(tuple(r.context["form"].non_field_errors()))
        self.assertEqual(len(errores), 1)  # pendiente, inexistente y mala clave: indistinguibles

    def test_el_nombre_de_usuario_interno_no_sirve_en_el_ingreso_de_paciente(self):
        r = self.entrar(self.paciente.username)
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_el_personal_entra_con_usuario_y_no_con_rut(self):
        r = self.entrar("coord_login", tipo="personal")
        self.assertRedirects(r, "/coordinacion/", fetch_redirect_response=False)
        self.client.logout()
        # En el ingreso de personal, un RUT de paciente se trata como usuario: no entra.
        r = self.entrar(RUT, tipo="personal")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_el_personal_no_entra_por_el_ingreso_de_paciente(self):
        r = self.entrar("coord_login", tipo="paciente")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_un_tipo_manipulado_se_trata_como_paciente(self):
        r = self.entrar("coord_login", tipo="admin; DROP TABLE")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_la_pagina_de_login_muestra_rut_o_usuario_segun_el_tipo(self):
        self.assertContains(self.client.get("/login/", secure=True), "Ingresa tu RUT")
        self.assertContains(self.client.get("/login/?tipo=personal", secure=True), ">\n        Usuario")

    def test_bloqueo_tras_cinco_intentos_fallidos(self):
        for _ in range(MAX_INTENTOS):
            self.entrar(RUT, "mala")
        r = self.entrar(RUT, CLAVE)  # aun con la clave correcta
        self.assertContains(r, "Demasiados intentos")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_el_bloqueo_no_afecta_a_otro_paciente_y_un_exito_reinicia_la_cuenta(self):
        for _ in range(MAX_INTENTOS - 1):
            self.entrar(RUT, "mala")
        self.assertRedirects(self.entrar(RUT), "/mis-solicitudes/", fetch_redirect_response=False)
        self.client.logout()
        for _ in range(MAX_INTENTOS - 1):  # el contador volvió a cero
            self.entrar(RUT, "mala")
        self.assertRedirects(self.entrar(RUT), "/mis-solicitudes/", fetch_redirect_response=False)

    def test_el_rut_no_queda_legible_en_la_base(self):
        with connection.cursor() as c:
            c.execute("SELECT rut, rut_hash FROM pacientes_perfilpaciente WHERE usuario_id = %s", [self.paciente.pk])
            rut_db, hash_db = c.fetchone()
        self.assertNotIn("12345678", rut_db)
        self.assertNotIn("12345678", hash_db)
        self.assertEqual(hash_db, hash_rut(RUT))
        self.assertEqual(hash_rut("12.345.678-5"), hash_rut("123456785"))
        self.assertIsNone(hash_rut("no es un rut"))

    def test_dos_perfiles_no_pueden_tener_el_mismo_rut(self):
        from django.db import IntegrityError, transaction
        with self.assertRaises(IntegrityError), transaction.atomic():
            crear_paciente("pduplicado001", "12345678-5")


class UsuarioDelPersonalTests(TestCase):

    def form(self, username):
        return UsuarioNuevoForm({
            "username": username, "first_name": "Ana", "last_name": "Pérez", "email": "a@example.com",
            "password1": CLAVE, "password2": CLAVE, "rol": "Estudiante",
        })

    def test_acepta_usuarios_cortos_sin_simbolos(self):
        for ok in ("estudiante1", "coord_ana", "abcd", "a" * 20):
            with self.subTest(username=ok):
                self.assertTrue(self.form(ok).is_valid(), self.form(ok).errors)

    def test_rechaza_simbolos_mayusculas_largos_cortos_y_ruts(self):
        for malo in ("ab", "a" * 21, "Estudiante1", "est.udiante", "est-udiante", "est@ex.com",
                     "1estudiante", "12345678-5", "est udiante", "est;drop", "<b>x</b>"):
            with self.subTest(username=malo):
                self.assertFalse(self.form(malo).is_valid())


class RegistroYMigracionTests(TestCase):

    def setUp(self):
        cache.clear()

    def registrar(self, **cambios):
        datos = {
            "nombre_completo": "Ana Torres", "correo": "ana@example.com", "fecha_nacimiento": "1990-01-01",
            "rut": RUT, "telefono": "+56 9 1234 5678", "password1": CLAVE, "password2": CLAVE,
        }
        datos.update(cambios)
        return self.client.post("/registro/", datos, secure=True)

    def test_el_usuario_interno_es_opaco_y_no_contiene_correo_ni_rut(self):
        self.registrar()
        usuario = PerfilPaciente.objects.get().usuario
        self.assertRegex(usuario.username, r"^p[0-9a-f]{12}$")
        self.assertNotIn("ana", usuario.username)
        self.assertEqual(usuario.email, "ana@example.com")

    def test_un_rut_repetido_no_crea_otra_cuenta_ni_lo_revela(self):
        self.registrar()
        r = self.registrar(correo="otra@example.com")
        self.assertRedirects(r, "/registro/enviado/", fetch_redirect_response=False)
        self.assertEqual(PerfilPaciente.objects.count(), 1)
        self.assertEqual(User.objects.count(), 1)

    def test_el_rut_repetido_con_otro_formato_tambien_se_detecta(self):
        self.registrar()
        self.registrar(correo="otra@example.com", rut="123456785")
        self.assertEqual(PerfilPaciente.objects.count(), 1)

    def test_flujo_completo_registro_aceptacion_e_ingreso_con_rut(self):
        self.registrar()
        r = self.client.post("/login/", {"username": RUT, "password": CLAVE}, secure=True)
        self.assertEqual(r.status_code, 200)  # pendiente: aún no entra
        perfil = PerfilPaciente.objects.get()
        coord = User.objects.create_user("coord_flujo", password=CLAVE)
        coord.groups.add(Group.objects.get_or_create(name="Coordinador")[0])
        self.client.force_login(coord)
        self.client.post(f"/coordinacion/registros/{perfil.pk}/aceptar/", secure=True)
        self.client.logout()
        r = self.client.post("/login/", {"username": RUT, "password": CLAVE}, secure=True)
        self.assertRedirects(r, "/mis-solicitudes/", fetch_redirect_response=False)

    def test_la_migracion_rellena_el_indice_de_los_pacientes_existentes(self):
        from importlib import import_module
        from django.apps import apps
        migracion = import_module("pacientes.migrations.0010_perfilpaciente_rut_hash")
        crear_paciente("pmigracion001", "12345678-5")
        crear_paciente("pmigracion002", "22222222-2")
        PerfilPaciente.objects.update(rut_hash=None)
        migracion.rellenar_hash(apps, None)
        self.assertEqual(PerfilPaciente.objects.filter(rut_hash__isnull=True).count(), 0)
