# ============================================
# Paneles por rol: contenido, logo y página de inicio
# --------------------------------------------
# Al entrar, cada rol ve en el centro de la pantalla lo que necesita
# (conteos y listas cortas con accesos directos). El logo del menú lleva a
# la página principal del rol. El personal que abre "/" va a su panel.
# Los resúmenes no exponen RUT ni antecedentes, y el estudiante solo ve SUS
# casos. Las peticiones usan secure=True para no depender de DEBUG.
# ============================================

from datetime import date, timedelta

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.utils import timezone

from administracion.models import Especialidad
from pacientes.models import PerfilPaciente, Solicitud

CLAVE = "Clave-Segura#2026x"
RUT = "12345678-5"


class PanelesPorRolTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        g = {n: Group.objects.get_or_create(name=n)[0]
             for n in ("Coordinador", "Estudiante", "Paciente", "Super Administrador")}
        cls.coord = User.objects.create_user("pan_coord", password=CLAVE)
        cls.coord.groups.add(g["Coordinador"])
        cls.est = User.objects.create_user("pan_est", first_name="Elena", last_name="Soto", password=CLAVE)
        cls.est.groups.add(g["Estudiante"])
        cls.otro_est = User.objects.create_user("pan_otro_est", password=CLAVE)
        cls.otro_est.groups.add(g["Estudiante"])
        cls.est_inactivo = User.objects.create_user("pan_est_inactivo", password=CLAVE, is_active=False)
        cls.est_inactivo.groups.add(g["Estudiante"])
        cls.sa = User.objects.create_user("pan_sa", password=CLAVE)
        cls.sa.groups.add(g["Super Administrador"])
        cls.paciente = User.objects.create_user("pan_pac@example.com", password=CLAVE)
        cls.paciente.groups.add(g["Paciente"])
        PerfilPaciente.objects.create(
            usuario=cls.paciente, nombre_completo="Paciente Aceptada", fecha_nacimiento=date(1990, 1, 1),
            rut=RUT, telefono="+56 9 1234 5678", estado="ACEPTADO",
        )
        cls.pend = User.objects.create_user("pan_pend@example.com", password=CLAVE, is_active=False)
        PerfilPaciente.objects.create(
            usuario=cls.pend, nombre_completo="Registro Pendiente Uno", fecha_nacimiento=date(1991, 2, 2),
            rut="11111111-1", telefono="+56 9 1111 1111",
        )
        cls.esp = Especialidad.objects.create(nombre="Esp Panel (tests paneles)", activa=True)

    def solicitud(self, nombre, estado="PENDIENTE", estudiante=None):
        return Solicitud.objects.create(
            nombre_completo=nombre, fecha_nacimiento=date(1990, 1, 1), rut=RUT,
            telefono="+56 9 1234 5678", motivo_consulta="Dolor de muelas hace una semana",
            especialidad=self.esp, estado=estado, estudiante_asignado=estudiante,
            fecha_atencion=timezone.now() + timedelta(days=2) if estudiante else None,
        )

    def ver(self, usuario, url):
        self.client.force_login(usuario)
        return self.client.get(url, secure=True)

    # ---------- Coordinador ----------
    def test_panel_del_coordinador_muestra_conteos_y_listas(self):
        self.solicitud("Persona Pendiente Uno")
        self.solicitud("Persona Derivada", "DERIVADA", self.est)
        self.solicitud("Persona Realizada", "REALIZADO", self.est)
        r = self.ver(self.coord, "/coordinacion/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["registros_pendientes"], 1)
        self.assertEqual(r.context["conteos"], {"pendientes": 1, "derivadas": 1, "atendidas": 1})
        self.assertEqual(r.context["estudiantes_activos"], 2)
        self.assertContains(r, "Registro Pendiente Uno")
        self.assertContains(r, "Esp Panel (tests paneles)")
        for url in ("/coordinacion/registros/", "/coordinacion/listado/?estado=PENDIENTE",
                    "/coordinacion/listado/?estado=DERIVADA", "/coordinacion/estudiantes/"):
            self.assertContains(r, url)

    def test_el_panel_del_coordinador_no_muestra_rut(self):
        self.solicitud("Persona Pendiente Uno")
        r = self.ver(self.coord, "/coordinacion/")
        self.assertNotContains(r, "12345678")
        self.assertNotContains(r, "11111111")

    def test_el_panel_limita_las_listas_a_cinco_filas(self):
        for i in range(8):
            self.solicitud(f"Persona Numero {i}")
        r = self.ver(self.coord, "/coordinacion/")
        self.assertEqual(len(r.context["proximas_solicitudes"]), 5)
        self.assertEqual(r.context["conteos"]["pendientes"], 8)

    # ---------- lista de estudiantes ----------
    def test_lista_de_estudiantes_con_su_carga(self):
        self.solicitud("Caso A", "DERIVADA", self.est)
        self.solicitud("Caso B", "REALIZADO", self.est)
        self.solicitud("Caso C", "TERMINADO", self.est)
        r = self.ver(self.coord, "/coordinacion/estudiantes/")
        self.assertEqual(r.status_code, 200)
        nombres = {e.username: e for e in r.context["estudiantes"]}
        self.assertEqual(set(nombres), {"pan_est", "pan_otro_est"})  # sin inactivos ni otros roles
        e = nombres["pan_est"]
        self.assertEqual((e.por_atender, e.por_ficha, e.terminadas), (1, 1, 1))
        self.assertEqual(nombres["pan_otro_est"].por_atender, 0)
        self.assertContains(r, "Elena Soto")
        self.assertNotContains(r, "Caso A")  # no muestra datos de pacientes

    def test_lista_de_estudiantes_solo_para_coordinador_y_superadmin(self):
        for usuario in (self.est, self.paciente):
            with self.subTest(usuario=usuario.username):
                self.assertEqual(self.ver(usuario, "/coordinacion/estudiantes/").status_code, 403)
        self.client.logout()
        r = self.client.get("/coordinacion/estudiantes/", secure=True)
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.url.startswith("/login/"))
        self.assertEqual(self.ver(self.sa, "/coordinacion/estudiantes/").status_code, 200)

    # ---------- Estudiante ----------
    def test_panel_del_estudiante_muestra_solo_sus_casos(self):
        self.solicitud("Mi Paciente Derivado", "DERIVADA", self.est)
        self.solicitud("Mi Paciente Realizado", "REALIZADO", self.est)
        self.solicitud("Mi Paciente Terminado", "TERMINADO", self.est)
        self.solicitud("Paciente De Otro Estudiante", "DERIVADA", self.otro_est)
        self.solicitud("Paciente Sin Asignar")
        r = self.ver(self.est, "/estudiantes/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["conteos"], {"por_atender": 1, "por_ficha": 1, "terminadas": 1})
        self.assertContains(r, "Mi Paciente Derivado")
        self.assertContains(r, "Completar ficha")
        self.assertNotContains(r, "Mi Paciente Terminado")  # terminados no son "próximos"
        self.assertNotContains(r, "Paciente De Otro Estudiante")
        self.assertNotContains(r, "Paciente Sin Asignar")
        self.assertNotContains(r, "12345678")

    def test_panel_del_estudiante_vacio(self):
        r = self.ver(self.otro_est, "/estudiantes/")
        self.assertContains(r, "No tienes casos pendientes")

    # ---------- Administrador ----------
    def test_panel_del_administrador_muestra_conteos_y_accesos(self):
        r = self.ver(self.sa, "/administracion/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["registros_pendientes"], 1)
        self.assertEqual(r.context["usuarios_activos"], 5)
        self.assertEqual(r.context["usuarios_inactivos"], 2)
        for url in ("/administracion/usuarios/", "/administracion/especialidades/",
                    "/coordinacion/listado/", "/coordinacion/estudiantes/", "/coordinacion/registros/"):
            self.assertContains(r, url)

    # ---------- logo e inicio ----------
    def test_el_logo_lleva_a_la_pagina_principal_de_cada_rol(self):
        casos = {
            self.coord: "/coordinacion/", self.est: "/estudiantes/",
            self.sa: "/administracion/", self.paciente: "/mis-solicitudes/",
        }
        for usuario, destino in casos.items():
            with self.subTest(usuario=usuario.username):
                html = self.ver(usuario, destino).content.decode()
                self.assertIn(f'class="navbar-brand d-flex flex-column" href="{destino}"', html)
        self.client.logout()
        html = self.client.get("/", secure=True).content.decode()
        self.assertIn('class="navbar-brand d-flex flex-column" href="/"', html)

    def test_el_personal_que_abre_el_inicio_va_a_su_panel(self):
        casos = {self.coord: "/coordinacion/", self.est: "/estudiantes/", self.sa: "/administracion/"}
        for usuario, destino in casos.items():
            with self.subTest(usuario=usuario.username):
                r = self.ver(usuario, "/")
                self.assertRedirects(r, destino, fetch_redirect_response=False)

    def test_paciente_aceptado_ve_el_formulario_y_el_anonimo_la_bienvenida(self):
        r = self.ver(self.paciente, "/")
        self.assertContains(r, "Solicitud de atención odontológica")
        self.client.logout()
        r = self.client.get("/", secure=True)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Ingreso de pacientes")
        self.assertNotContains(r, "Solicitud de atención odontológica")

    def test_un_usuario_sin_rol_ve_la_bienvenida(self):
        sin_rol = User.objects.create_user("pan_sin_rol", password=CLAVE)
        self.assertContains(self.ver(sin_rol, "/"), "Ingreso de pacientes")

    def test_el_anonimo_no_puede_enviar_el_formulario(self):
        self.client.logout()
        r = self.client.post("/", {
            "nombre_completo": "Juan Anónimo", "fecha_nacimiento": "1985-05-05", "rut": "12.345.678-5",
            "telefono": "+56 9 8765 4321", "especialidad": self.esp.pk,
            "motivo_consulta": "Dolor de muelas hace una semana",
            "experiencia_previa": "", "antecedentes_personales": "", "antecedentes_familiares": "",
        }, secure=True)
        self.assertRedirects(r, "/login/", fetch_redirect_response=False)
        self.assertEqual(Solicitud.objects.count(), 0)
