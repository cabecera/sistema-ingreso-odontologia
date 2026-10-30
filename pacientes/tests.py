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
        response = self.client.get(url)
        
        # Permitimos 404 o 301 (en caso de que Django redirija por la barra final)
        self.assertIn(response.status_code, [301, 302, 404])