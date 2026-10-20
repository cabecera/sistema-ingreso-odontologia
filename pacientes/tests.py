from django.test import TestCase

class SeguridadPacientesTest(TestCase):
    def test_acceso_no_autorizado_a_pacientes(self):
        url = '/administracion/'
        response = self.client.get(url, secure=True)

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith('/login/') or response.url.startswith('/accounts/login/'))