# ============================================
# AB#83 (REQ-17): Login del paciente y reserva con sesión iniciada
# --------------------------------------------
# Comprueba que el paciente aceptado entra y llega a "Mis solicitudes",
# que reserva con los datos de su perfil (sin poder falsearlos), que solo
# ve sus propias solicitudes, que no puede tener dos solicitudes en curso
# para la misma especialidad y que el formulario público sigue funcionando.
# Las peticiones usan secure=True para no depender de DEBUG.
# ============================================

from datetime import date

from django.contrib.auth.models import Group, User
from django.test import TestCase

from administracion.models import Especialidad
from pacientes.models import PerfilPaciente, Solicitud
from seguridad.models import BitacoraAuditoria

CLAVE = "Clave-Segura#2026x"


class ReservaPacienteTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.grupo_paciente = Group.objects.get_or_create(name="Paciente")[0]
        for nombre in ("Coordinador", "Estudiante"):
            Group.objects.get_or_create(name=nombre)
        cls.esp_a = Especialidad.objects.create(nombre="Esp A (tests reserva)", activa=True)
        cls.esp_b = Especialidad.objects.create(nombre="Esp B (tests reserva)", activa=True)
        cls.paciente = cls.crear_paciente("pac.a@example.com", "María José Pérez", "12345678-5")
        cls.otro = cls.crear_paciente("pac.b@example.com", "Luis Soto Rojas", "11111111-1")
        cls.coordinador = User.objects.create_user("coord_res", password=CLAVE)
        cls.coordinador.groups.add(Group.objects.get(name="Coordinador"))
        cls.estudiante = User.objects.create_user("est_res", password=CLAVE)
        cls.estudiante.groups.add(Group.objects.get(name="Estudiante"))

    @classmethod
    def crear_paciente(cls, correo, nombre, rut, estado="ACEPTADO", activo=True):
        usuario = User.objects.create_user(correo, email=correo, password=CLAVE, is_active=activo)
        usuario.groups.add(cls.grupo_paciente)
        PerfilPaciente.objects.create(
            usuario=usuario, nombre_completo=nombre, fecha_nacimiento=date(1990, 1, 1),
            rut=rut, telefono="+56 9 1234 5678", estado=estado,
        )
        return usuario

    def datos(self, especialidad=None, **extra):
        base = {
            "especialidad": (especialidad or self.esp_a).pk,
            "motivo_consulta": "Dolor de muelas hace una semana",
            "experiencia_previa": "", "antecedentes_personales": "", "antecedentes_familiares": "",
        }
        base.update(extra)
        return base

    def reservar(self, **kw):
        return self.client.post("/", self.datos(**kw), secure=True)

    # ---------- login por rol ----------
    def test_paciente_aceptado_inicia_sesion_y_va_a_mis_solicitudes(self):
        r = self.client.post("/login/", {"username": "pac.a@example.com", "password": CLAVE}, secure=True)
        self.assertRedirects(r, "/mis-solicitudes/", fetch_redirect_response=False)

    def test_el_coordinador_va_a_su_panel(self):
        r = self.client.post("/login/", {"username": "coord_res", "password": CLAVE}, secure=True)
        self.assertRedirects(r, "/coordinacion/", fetch_redirect_response=False)

    def test_next_manda_y_un_destino_externo_se_ignora(self):
        r = self.client.post("/login/?next=/coordinacion/", {"username": "coord_res", "password": CLAVE}, secure=True)
        self.assertRedirects(r, "/coordinacion/", fetch_redirect_response=False)
        self.client.logout()
        r = self.client.post("/login/?next=https://malo.example.com/",
                             {"username": "pac.a@example.com", "password": CLAVE}, secure=True)
        self.assertRedirects(r, "/mis-solicitudes/", fetch_redirect_response=False)

    def test_pendiente_o_rechazado_no_inician_sesion(self):
        self.crear_paciente("pend@example.com", "Ana Pendiente", "22222222-2", estado="PENDIENTE", activo=False)
        self.crear_paciente("rech@example.com", "Rosa Rechazada", "33333333-3", estado="RECHAZADO", activo=False)
        for correo in ("pend@example.com", "rech@example.com"):
            with self.subTest(correo=correo):
                r = self.client.post("/login/", {"username": correo, "password": CLAVE}, secure=True)
                self.assertEqual(r.status_code, 200)
                self.assertNotIn("_auth_user_id", self.client.session)

    # ---------- reserva con sesión ----------
    def test_reserva_usa_los_datos_del_perfil_y_queda_ligada_a_la_cuenta(self):
        self.client.force_login(self.paciente)
        r = self.reservar()
        self.assertRedirects(r, "/mis-solicitudes/", fetch_redirect_response=False)
        s = Solicitud.objects.get()
        self.assertEqual(s.paciente, self.paciente)
        self.assertEqual(s.nombre_completo, "María José Pérez")
        self.assertEqual(s.rut, "12345678-5")
        self.assertEqual(s.telefono, "+56 9 1234 5678")
        self.assertEqual(s.estado, "PENDIENTE")

    def test_el_paciente_no_puede_falsear_sus_datos(self):
        self.client.force_login(self.paciente)
        self.reservar(nombre_completo="Otra Persona", rut="11.111.111-1", telefono="999999999",
                      paciente=self.otro.pk, estado="DERIVADA", estudiante_asignado=self.estudiante.pk)
        s = Solicitud.objects.get()
        self.assertEqual(s.paciente, self.paciente)
        self.assertEqual(s.nombre_completo, "María José Pérez")
        self.assertEqual(s.rut, "12345678-5")
        self.assertEqual(s.estado, "PENDIENTE")
        self.assertIsNone(s.estudiante_asignado)

    def test_el_formulario_no_pide_datos_personales_al_paciente(self):
        self.client.force_login(self.paciente)
        r = self.client.get("/", secure=True)
        self.assertContains(r, "María José Pérez")
        for campo in ("nombre_completo", "rut", "telefono", "fecha_nacimiento"):
            self.assertNotContains(r, f'name="{campo}"')

    def test_no_se_permiten_dos_solicitudes_en_curso_para_la_misma_especialidad(self):
        self.client.force_login(self.paciente)
        self.reservar()
        r = self.reservar()
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Ya tienes una solicitud en curso")
        self.assertEqual(Solicitud.objects.count(), 1)

    def test_si_la_anterior_termino_o_es_otra_especialidad_si_se_permite(self):
        self.client.force_login(self.paciente)
        self.reservar()
        self.reservar(especialidad=self.esp_b)
        self.assertEqual(Solicitud.objects.count(), 2)
        Solicitud.objects.filter(especialidad=self.esp_a).update(estado="TERMINADO")
        self.reservar()
        self.assertEqual(Solicitud.objects.count(), 3)

    def test_la_regla_de_duplicados_es_por_paciente(self):
        self.client.force_login(self.paciente)
        self.reservar()
        self.client.force_login(self.otro)
        self.reservar()
        self.assertEqual(Solicitud.objects.count(), 2)

    def test_bitacora_de_la_reserva_sin_datos_personales(self):
        self.client.force_login(self.paciente)
        self.reservar()
        registro = BitacoraAuditoria.objects.get(accion="Solicitud ingresada por paciente")
        texto = f"{registro.accion} {registro.detalles}".lower()
        for dato in ("pac.a", "maría", "pérez", "12345678", "dolor"):
            self.assertNotIn(dato, texto)

    def test_el_anonimo_no_puede_reservar_sin_registro_aceptado(self):
        # Flujo del profesor: primero registro, revisión y aceptación.
        r = self.client.post("/", {
            **self.datos(), "nombre_completo": "Juan Anónimo", "fecha_nacimiento": "1985-05-05",
            "rut": "12.345.678-5", "telefono": "+56 9 8765 4321",
        }, secure=True)
        self.assertRedirects(r, "/login/", fetch_redirect_response=False)
        self.assertEqual(Solicitud.objects.count(), 0)

    def test_el_anonimo_ve_bienvenida_con_registro_y_login_no_el_formulario(self):
        r = self.client.get("/", secure=True)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "/registro/")
        self.assertContains(r, "/login/")
        self.assertNotContains(r, 'name="motivo_consulta"')

    def test_paciente_con_registro_pendiente_o_rechazado_no_puede_reservar(self):
        for estado in ("PENDIENTE", "RECHAZADO"):
            usuario = self.crear_paciente(f"{estado.lower()}@example.com", "Sin Aceptar", "22222222-2",
                                          estado=estado)
            self.client.force_login(usuario)
            with self.subTest(estado=estado):
                r = self.reservar()
                self.assertEqual(r.status_code, 302)
                self.assertEqual(Solicitud.objects.count(), 0)

    # ---------- Mis solicitudes ----------
    def test_mis_solicitudes_exige_sesion_y_rol_paciente(self):
        r = self.client.get("/mis-solicitudes/", secure=True)
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.url.startswith("/login/"))
        for usuario in (self.coordinador, self.estudiante):
            self.client.force_login(usuario)
            with self.subTest(usuario=usuario.username):
                self.assertEqual(self.client.get("/mis-solicitudes/", secure=True).status_code, 403)

    def test_solo_ve_sus_propias_solicitudes(self):
        self.client.force_login(self.otro)
        self.reservar(especialidad=self.esp_b)
        self.client.force_login(self.paciente)
        self.reservar(especialidad=self.esp_a)
        r = self.client.get("/mis-solicitudes/", secure=True)
        self.assertContains(r, "Esp A (tests reserva)")
        self.assertNotContains(r, "Esp B (tests reserva)")

    def test_muestra_el_horario_cuando_ya_fue_derivada(self):
        from django.utils import timezone
        from datetime import timedelta
        self.client.force_login(self.paciente)
        self.reservar()
        futuro = timezone.now() + timedelta(days=3)
        Solicitud.objects.update(estado="DERIVADA", fecha_atencion=futuro)
        r = self.client.get("/mis-solicitudes/", secure=True)
        self.assertContains(r, "Derivada")
        self.assertContains(r, timezone.localtime(futuro).strftime("%d/%m/%Y %H:%M"))

    def test_no_expone_datos_del_estudiante_ni_antecedentes(self):
        self.client.force_login(self.paciente)
        self.reservar(antecedentes_personales="Alergia secreta")
        Solicitud.objects.update(estudiante_asignado=self.estudiante)
        r = self.client.get("/mis-solicitudes/", secure=True)
        self.assertNotContains(r, "est_res")
        self.assertNotContains(r, "Alergia secreta")

    def test_el_paciente_no_puede_abrir_el_detalle_de_estudiantes(self):
        self.client.force_login(self.paciente)
        self.reservar()
        pk = Solicitud.objects.get().pk
        self.assertEqual(self.client.get(f"/detalle/{pk}/", secure=True).status_code, 404)

    def test_el_paciente_no_entra_a_paginas_del_personal(self):
        self.client.force_login(self.paciente)
        for url in ("/coordinacion/", "/coordinacion/registros/", "/administracion/", "/estudiantes/mis-pacientes/"):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url, secure=True).status_code, 403)

    def test_el_menu_muestra_mis_solicitudes_solo_al_paciente(self):
        r = self.client.get("/", secure=True)
        self.assertNotContains(r, "Mis solicitudes")
        self.client.force_login(self.coordinador)
        self.assertNotContains(self.client.get("/", secure=True, follow=True), "Mis solicitudes")
        self.client.force_login(self.paciente)
        self.assertContains(self.client.get("/", secure=True), "Mis solicitudes")
