from django.contrib.auth.models import User
from django.test import TestCase

from administracion.models import Especialidad
from pacientes.models import Solicitud


class SolicitudAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.root = User.objects.create_superuser("adm_root", "a@example.com", "Clave-Segura#2026x")
        esp = Especialidad.objects.create(nombre="Esp admin (tests)", activa=True)
        cls.s = Solicitud.objects.create(
            nombre_completo="Persona Secreta", fecha_nacimiento="1990-01-01", rut="12345678-5",
            telefono="+56 9 1234 5678", especialidad=esp, motivo_consulta="Dolor",
        )

    def setUp(self):
        self.client.force_login(self.root)

    def test_aparece_en_el_admin_y_no_muestra_datos_personales(self):
        lista = self.client.get("/admin/pacientes/solicitud/", secure=True)
        self.assertEqual(lista.status_code, 200)
        detalle = self.client.get(f"/admin/pacientes/solicitud/{self.s.pk}/change/", secure=True)
        for r in (lista, detalle):
            self.assertNotContains(r, "Persona Secreta")
            self.assertNotContains(r, "12345678")

    def test_no_se_puede_crear_ni_editar(self):
        self.assertEqual(self.client.get("/admin/pacientes/solicitud/add/", secure=True).status_code, 403)
        r = self.client.post(f"/admin/pacientes/solicitud/{self.s.pk}/change/", {"estado": "TERMINADO"}, secure=True)
        self.assertEqual(r.status_code, 403)

    def test_se_puede_borrar_para_limpiar_datos_de_prueba(self):
        r = self.client.post(f"/admin/pacientes/solicitud/{self.s.pk}/delete/", {"post": "yes"}, secure=True)
        self.assertEqual(r.status_code, 302)
        self.assertFalse(Solicitud.objects.filter(pk=self.s.pk).exists())
