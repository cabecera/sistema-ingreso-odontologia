# ============================================
# AB#84 (REQ-17): Revisión de registros de pacientes por el Coordinador
# --------------------------------------------
# Comprueba el control de acceso, que aceptar activa la cuenta (y el
# paciente puede entrar), que rechazar la deja inactiva, que un registro
# no se revisa dos veces, que las acciones exigen POST + CSRF, que el
# Super Administrador no puede activar a un paciente sin revisión y que
# la bitácora no guarda datos personales.
# Las peticiones usan secure=True para no depender de DEBUG.
# ============================================

from datetime import date

from django.contrib.auth.models import Group, User
from django.core import mail
from django.test import Client, TestCase

from pacientes.models import PerfilPaciente
from seguridad.models import BitacoraAuditoria

CLAVE = "Clave-Segura#2026x"
CORREO = "paciente.revision@example.com"


class RevisionRegistrosTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        grupos = {n: Group.objects.get_or_create(name=n)[0]
                  for n in ("Coordinador", "Estudiante", "Super Administrador", "Paciente")}
        cls.coordinador = User.objects.create_user("coord_rev", password=CLAVE)
        cls.coordinador.groups.add(grupos["Coordinador"])
        cls.estudiante = User.objects.create_user("est_rev", password=CLAVE)
        cls.estudiante.groups.add(grupos["Estudiante"])
        cls.super_admin = User.objects.create_user("sa_rev", password=CLAVE)
        cls.super_admin.groups.add(grupos["Super Administrador"])
        cls.grupo_paciente = grupos["Paciente"]

    def crear_perfil(self, correo=CORREO, nombre="María José Pérez"):
        usuario = User.objects.create_user(
            correo, email=correo, password=CLAVE, is_active=False
        )
        usuario.groups.add(self.grupo_paciente)
        return PerfilPaciente.objects.create(
            usuario=usuario, nombre_completo=nombre,
            fecha_nacimiento=date(1990, 1, 1), rut="12345678-5",
            telefono="+56 9 1234 5678",
        )

    def post(self, nombre, perfil):
        return self.client.post(f"/coordinacion/registros/{perfil.pk}/{nombre}/", secure=True)

    # ---------- acceso ----------
    def test_anonimo_es_redirigido_al_login(self):
        perfil = self.crear_perfil()
        for url in ("/coordinacion/registros/",):
            r = self.client.get(url, secure=True)
            self.assertEqual(r.status_code, 302)
            self.assertTrue(r.url.startswith("/login/"))
        for accion in ("aceptar", "rechazar"):
            r = self.post(accion, perfil)
            self.assertEqual(r.status_code, 302)
            self.assertTrue(r.url.startswith("/login/"))
        perfil.refresh_from_db()
        self.assertEqual(perfil.estado, "PENDIENTE")

    def test_otros_roles_reciben_403_y_no_cambian_nada(self):
        perfil = self.crear_perfil()
        paciente_activo = User.objects.create_user("pac_activo", password=CLAVE)
        paciente_activo.groups.add(self.grupo_paciente)
        for usuario in (self.estudiante, paciente_activo):
            self.client.force_login(usuario)
            with self.subTest(usuario=usuario.username):
                self.assertEqual(self.client.get("/coordinacion/registros/", secure=True).status_code, 403)
                self.assertEqual(self.post("aceptar", perfil).status_code, 403)
                self.assertEqual(self.post("rechazar", perfil).status_code, 403)
        perfil.refresh_from_db()
        self.assertEqual(perfil.estado, "PENDIENTE")
        self.assertFalse(perfil.usuario.is_active)

    def test_coordinador_ve_el_listado(self):
        self.crear_perfil()
        self.client.force_login(self.coordinador)
        r = self.client.get("/coordinacion/registros/", secure=True)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, CORREO)

    def test_filtro_invalido_se_ignora_y_no_se_refleja(self):
        self.client.force_login(self.coordinador)
        r = self.client.get("/coordinacion/registros/?estado=<script>alert(1)</script>", secure=True)
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, "<script>alert(1)</script>")

    def test_filtro_por_estado(self):
        pendiente = self.crear_perfil("pend@example.com", "Ana Pendiente")
        aceptado = self.crear_perfil("acep@example.com", "Beatriz Aceptada")
        aceptado.estado = "ACEPTADO"; aceptado.save()
        self.client.force_login(self.coordinador)
        r = self.client.get("/coordinacion/registros/?estado=ACEPTADO", secure=True)
        self.assertContains(r, "Beatriz Aceptada")
        self.assertNotContains(r, "Ana Pendiente")
        r = self.client.get("/coordinacion/registros/", secure=True)
        self.assertContains(r, "Ana Pendiente")

    # ---------- aceptar ----------
    def test_aceptar_activa_la_cuenta_y_el_paciente_puede_entrar(self):
        perfil = self.crear_perfil()
        self.assertFalse(self.client.login(username=CORREO, password=CLAVE))
        self.client.force_login(self.coordinador)
        r = self.post("aceptar", perfil)
        self.assertRedirects(r, "/coordinacion/registros/", fetch_redirect_response=False)
        perfil.refresh_from_db(); perfil.usuario.refresh_from_db()
        self.assertEqual(perfil.estado, "ACEPTADO")
        self.assertTrue(perfil.usuario.is_active)
        self.assertEqual(perfil.revisado_por, self.coordinador)
        self.assertIsNotNone(perfil.fecha_revision)
        # Ahora sí puede iniciar sesión (con la misma contraseña que eligió).
        self.client.logout()
        self.assertTrue(self.client.login(username=CORREO, password=CLAVE))

    def test_aceptar_envia_correo_sin_datos_sensibles(self):
        perfil = self.crear_perfil()
        self.client.force_login(self.coordinador)
        self.post("aceptar", perfil)
        self.assertEqual(len(mail.outbox), 1)
        correo = mail.outbox[0]
        self.assertEqual(correo.to, [CORREO])
        self.assertIn("/login/", correo.body)
        self.assertNotIn(CLAVE, correo.body)
        self.assertNotIn("12345678", correo.body)

    # ---------- rechazar ----------
    def test_rechazar_deja_la_cuenta_inactiva(self):
        perfil = self.crear_perfil()
        self.client.force_login(self.coordinador)
        self.post("rechazar", perfil)
        perfil.refresh_from_db(); perfil.usuario.refresh_from_db()
        self.assertEqual(perfil.estado, "RECHAZADO")
        self.assertFalse(perfil.usuario.is_active)
        self.assertEqual(perfil.revisado_por, self.coordinador)
        self.client.logout()
        self.assertFalse(self.client.login(username=CORREO, password=CLAVE))
        self.assertEqual(len(mail.outbox), 1)
        self.assertNotIn("/login/", mail.outbox[0].body)

    # ---------- reglas ----------
    def test_un_registro_revisado_no_se_puede_revisar_de_nuevo(self):
        perfil = self.crear_perfil()
        self.client.force_login(self.coordinador)
        self.post("rechazar", perfil)
        mail.outbox.clear()
        # Intentar aceptarlo después no lo reactiva.
        self.post("aceptar", perfil)
        perfil.refresh_from_db(); perfil.usuario.refresh_from_db()
        self.assertEqual(perfil.estado, "RECHAZADO")
        self.assertFalse(perfil.usuario.is_active)
        self.assertEqual(len(mail.outbox), 0)

    def test_aceptado_no_se_puede_rechazar_despues(self):
        perfil = self.crear_perfil()
        self.client.force_login(self.coordinador)
        self.post("aceptar", perfil)
        self.post("rechazar", perfil)
        perfil.refresh_from_db(); perfil.usuario.refresh_from_db()
        self.assertEqual(perfil.estado, "ACEPTADO")
        self.assertTrue(perfil.usuario.is_active)

    def test_registro_inexistente_da_404(self):
        self.client.force_login(self.coordinador)
        r = self.client.post("/coordinacion/registros/99999/aceptar/", secure=True)
        self.assertEqual(r.status_code, 404)

    def test_get_no_cambia_nada(self):
        perfil = self.crear_perfil()
        self.client.force_login(self.coordinador)
        for accion in ("aceptar", "rechazar"):
            r = self.client.get(f"/coordinacion/registros/{perfil.pk}/{accion}/", secure=True)
            self.assertEqual(r.status_code, 405)
        perfil.refresh_from_db()
        self.assertEqual(perfil.estado, "PENDIENTE")

    def test_sin_csrf_se_rechaza(self):
        perfil = self.crear_perfil()
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.coordinador)
        r = cliente.post(f"/coordinacion/registros/{perfil.pk}/aceptar/", secure=True)
        self.assertEqual(r.status_code, 403)
        perfil.refresh_from_db()
        self.assertEqual(perfil.estado, "PENDIENTE")

    def test_super_administrador_tambien_puede_revisar(self):
        perfil = self.crear_perfil()
        self.client.force_login(self.super_admin)
        self.post("aceptar", perfil)
        perfil.refresh_from_db()
        self.assertEqual(perfil.estado, "ACEPTADO")

    def test_falla_el_correo_pero_la_revision_se_guarda(self):
        from unittest import mock
        perfil = self.crear_perfil()
        self.client.force_login(self.coordinador)
        with mock.patch("coordinacion.views.send_mail", side_effect=OSError("smtp caído")):
            r = self.post("aceptar", perfil)
        self.assertEqual(r.status_code, 302)
        perfil.refresh_from_db()
        self.assertEqual(perfil.estado, "ACEPTADO")

    def test_bitacora_sin_datos_personales(self):
        perfil = self.crear_perfil()
        self.client.force_login(self.coordinador)
        self.post("aceptar", perfil)
        registro = BitacoraAuditoria.objects.get(accion="Registro de paciente aceptado")
        self.assertEqual(registro.usuario, self.coordinador)
        texto = f"{registro.accion} {registro.detalles}".lower()
        for dato in ("paciente.revision", "maría", "pérez", "12345678"):
            self.assertNotIn(dato, texto)

    # ---------- Super Administrador no se salta la revisión ----------
    def test_super_admin_no_puede_activar_paciente_sin_revision(self):
        perfil = self.crear_perfil()
        self.client.force_login(self.super_admin)
        r = self.client.post(
            f"/administracion/usuarios/{perfil.usuario.pk}/estado/", secure=True
        )
        self.assertEqual(r.status_code, 302)
        perfil.usuario.refresh_from_db()
        self.assertFalse(perfil.usuario.is_active)

    def test_super_admin_si_puede_desactivar_un_paciente_aceptado(self):
        perfil = self.crear_perfil()
        self.client.force_login(self.coordinador)
        self.post("aceptar", perfil)
        self.client.force_login(self.super_admin)
        self.client.post(f"/administracion/usuarios/{perfil.usuario.pk}/estado/", secure=True)
        perfil.usuario.refresh_from_db()
        self.assertFalse(perfil.usuario.is_active)

    def test_panel_muestra_registros_pendientes(self):
        self.crear_perfil()
        self.client.force_login(self.coordinador)
        r = self.client.get("/coordinacion/", secure=True)
        self.assertContains(r, "Registros por revisar")
        self.assertEqual(r.context["registros_pendientes"], 1)
