from datetime import date

from django.test import TestCase
from django.contrib.auth.models import User
from django.urls import reverse
from .models import Solicitud
from administracion.models import Especialidad

class SeguridadPacientesTest(TestCase):
    def test_acceso_no_autorizado_a_pacientes(self):
        url = '/administracion/'
        response = self.client.get(url, secure=True)

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith('/login/') or response.url.startswith('/accounts/login/'))

    def test_estudiante_no_puede_ver_caso_de_otro_companero(self):
        especialidad_test, _ = Especialidad.objects.get_or_create(
            nombre="Ortodoncia",
            defaults={"activa": True}
        )

        # 1. Crear dos usuarios estudiantes distintos
        estudiante1 = User.objects.create_user(username="alumno1", password="password123")
        estudiante2 = User.objects.create_user(username="alumno2", password="password123")

        # 2. Crear una solicitud asignada al estudiante 2 usando la especialidad
        solicitud_otro = Solicitud.objects.create(
            nombre_completo="Paciente Ajeno",
            rut="12345678-9",
            telefono="56912345678",
            fecha_nacimiento="1995-05-15",
            especialidad=especialidad_test,
            motivo_consulta="Consulta general",
            estudiante_asignado=estudiante2
        )

        # 3. Iniciar sesión como el estudiante 1
        self.client.login(username="alumno1", password="password123")

        # 4. Intentar acceder al detalle de la solicitud del otro compañero
        url = reverse("pacientes:detalle_paciente", args=[solicitud_otro.pk])
        response = self.client.get(url, secure=True)

        # Debe ser exactamente 404. Antes se aceptaba [301, 302, 404], pero
        # un 302 (redirige al login) o un 301 (redirección a HTTPS) harían
        # pasar el test sin que la vista haya decidido nada.
        self.assertEqual(response.status_code, 404)


# ============================================
# Task 51: Verificar que no vea pacientes ajenos
# --------------------------------------------
# Cubre el caso que faltaba: el estudiante al que SÍ le asignaron el
# paciente debe poder ver la página (antes fallaba con
# TemplateDoesNotExist y ningún test lo detectaba), además de los
# casos de rechazo. Se usa secure=True para que los tests no dependan
# de si DEBUG está activo (con DEBUG=False el sitio redirige a HTTPS).
# ============================================
class DetallePacienteTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        # Nombre distinto al catálogo real (cargado por migración y con
        # nombre único) para no chocar con las especialidades existentes.
        cls.especialidad = Especialidad.objects.create(
            nombre="Especialidad de Prueba (tests detalle paciente)",
            activa=True,
        )
        cls.estudiante = User.objects.create_user(
            username="alumno_asignado", password="password123"
        )
        cls.otro_estudiante = User.objects.create_user(
            username="alumno_ajeno", password="password123"
        )
        cls.solicitud = Solicitud.objects.create(
            nombre_completo="Paciente Asignado Prueba",
            rut="12345678-5",
            telefono="+56912345678",
            fecha_nacimiento=date(1995, 5, 15),
            especialidad=cls.especialidad,
            motivo_consulta="Consulta general",
            antecedentes_personales="ANTECEDENTE-SENSIBLE-XYZ",
            estudiante_asignado=cls.estudiante,
        )
        cls.url = reverse("pacientes:detalle_paciente", args=[cls.solicitud.pk])

    def test_estudiante_asignado_ve_su_paciente(self):
        self.client.login(username="alumno_asignado", password="password123")
        response = self.client.get(self.url, secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "pacientes/detalle_paciente.html")
        self.assertContains(response, "Paciente Asignado Prueba")

    def test_estudiante_ajeno_recibe_404(self):
        self.client.login(username="alumno_ajeno", password="password123")
        response = self.client.get(self.url, secure=True)
        self.assertEqual(response.status_code, 404)

    def test_sin_sesion_redirige_al_login(self):
        response = self.client.get(self.url, secure=True)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("/login/"))

    def test_id_inexistente_recibe_404(self):
        self.client.login(username="alumno_asignado", password="password123")
        url = reverse("pacientes:detalle_paciente", args=[999999])
        response = self.client.get(url, secure=True)
        self.assertEqual(response.status_code, 404)

    def test_detalle_no_muestra_antecedentes_de_salud(self):
        # Minimización de datos (REQ-08): el detalle no expone antecedentes.
        self.client.login(username="alumno_asignado", password="password123")
        response = self.client.get(self.url, secure=True)
        self.assertNotContains(response, "ANTECEDENTE-SENSIBLE-XYZ")
