# Ficha de la solicitud (lo que llena el paciente): lectura para coordinación
# y para el estudiante asignado, con control de acceso y sin fuga entre casos.
from datetime import date

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from administracion.models import Especialidad
from pacientes.models import Solicitud
from seguridad.models import BitacoraAuditoria


class VerFichaSolicitudTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        g_est, _ = Group.objects.get_or_create(name="Estudiante")
        g_coo, _ = Group.objects.get_or_create(name="Coordinador")
        g_sup, _ = Group.objects.get_or_create(name="Super Administrador")
        cls.est_a = User.objects.create_user(username="ficha_est_a")
        cls.est_a.groups.add(g_est)
        cls.est_b = User.objects.create_user(username="ficha_est_b")
        cls.est_b.groups.add(g_est)
        cls.coord = User.objects.create_user(username="ficha_coord")
        cls.coord.groups.add(g_coo)
        cls.admin = User.objects.create_user(username="ficha_admin")
        cls.admin.groups.add(g_sup)
        cls.sin_rol = User.objects.create_user(username="ficha_sinrol")

        esp = Especialidad.objects.create(nombre="Especialidad ficha")
        cls.sol = Solicitud.objects.create(
            nombre_completo="Paciente Ficha",
            fecha_nacimiento=date(1990, 1, 1),
            rut="55555555-5",
            telefono="+56911111111",
            motivo_consulta="Dolor molar\nsuperior derecho",
            experiencia_previa="Limpieza anual",
            antecedentes_personales="Alergia a penicilina",
            antecedentes_familiares="Diabetes en la familia",
            especialidad=esp,
            estudiante_asignado=cls.est_a,
        )
        cls.url_coord = reverse("coordinacion:ver_solicitud", args=[cls.sol.pk])
        cls.url_est = reverse("estudiantes:ver_solicitud", args=[cls.sol.pk])

    def _get(self, url, usuario=None):
        if usuario is not None:
            self.client.force_login(usuario)
        return self.client.get(url, secure=True)

    # ---------- Coordinación ----------

    def test_coordinador_ve_la_ficha_completa(self):
        r = self._get(self.url_coord, self.coord)
        self.assertEqual(r.status_code, 200)
        for texto in ("Paciente Ficha", "55555555-5", "Dolor molar",
                      "Limpieza anual", "Alergia a penicilina",
                      "Diabetes en la familia"):
            self.assertContains(r, texto)

    def test_super_administrador_ve_la_ficha(self):
        self.assertEqual(self._get(self.url_coord, self.admin).status_code, 200)

    def test_anonimo_a_coordinacion_va_al_login(self):
        r = self._get(self.url_coord)
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login/", r["Location"])

    def test_estudiante_no_entra_por_la_ruta_de_coordinacion(self):
        self.assertEqual(self._get(self.url_coord, self.est_a).status_code, 403)

    def test_sin_rol_no_entra_a_coordinacion(self):
        self.assertEqual(self._get(self.url_coord, self.sin_rol).status_code, 403)

    def test_solicitud_inexistente_da_404(self):
        url = reverse("coordinacion:ver_solicitud", args=[999999])
        self.assertEqual(self._get(url, self.coord).status_code, 404)

    def test_ficha_es_solo_lectura(self):
        self.client.force_login(self.coord)
        r = self.client.post(self.url_coord, secure=True)
        self.assertEqual(r.status_code, 405)

    # ---------- Estudiante ----------

    def test_estudiante_asignado_ve_la_ficha(self):
        r = self._get(self.url_est, self.est_a)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Alergia a penicilina")

    def test_otro_estudiante_recibe_404(self):
        self.assertEqual(self._get(self.url_est, self.est_b).status_code, 404)

    def test_anonimo_a_estudiantes_va_al_login(self):
        r = self._get(self.url_est)
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login/", r["Location"])

    def test_coordinador_no_entra_por_la_ruta_de_estudiante(self):
        self.assertEqual(self._get(self.url_est, self.coord).status_code, 403)

    def test_estudiante_ficha_solo_lectura(self):
        self.client.force_login(self.est_a)
        r = self.client.post(self.url_est, secure=True)
        self.assertEqual(r.status_code, 405)

    # ---------- Auditoría y escape ----------

    def test_consulta_queda_en_bitacora_sin_datos_personales(self):
        self._get(self.url_coord, self.coord)
        reg = BitacoraAuditoria.objects.get(accion="Ficha de solicitud consultada")
        self.assertEqual(reg.usuario, self.coord)
        for dato in ("55555555-5", "Paciente Ficha", "penicilina"):
            self.assertNotIn(dato, reg.detalles)

    def test_html_del_paciente_se_escapa(self):
        self.sol.motivo_consulta = "<script>alert(1)</script>"
        self.sol.save()
        r = self._get(self.url_coord, self.coord)
        self.assertNotContains(r, "<script>alert(1)</script>")
        self.assertContains(r, "&lt;script&gt;")

    # ---------- Botones ----------

    def test_listado_de_coordinacion_muestra_boton(self):
        r = self._get(reverse("coordinacion:listado_solicitudes"), self.coord)
        self.assertContains(r, self.url_coord)

    def test_mis_pacientes_muestra_boton(self):
        r = self._get(reverse("estudiantes:mis_pacientes"), self.est_a)
        self.assertContains(r, self.url_est)
