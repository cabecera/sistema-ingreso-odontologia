# ============================================
# Sesiones con duración limitada (OWASP A07)
# --------------------------------------------
# Verifica que la sesión no dure las dos semanas que Django da por defecto:
# vence por inactividad, se renueva con la actividad, se cierra al cerrar el
# navegador y que la cookie no la lee JavaScript.
# ============================================
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import Group, User
from django.contrib.sessions.models import Session
from django.test import TestCase
from django.utils import timezone

OCHO_HORAS = 8 * 60 * 60
CLAVE = "ClavePrueba#2026"


class ConfiguracionDeSesionTests(TestCase):
    def test_la_sesion_dura_como_maximo_ocho_horas(self):
        self.assertLessEqual(settings.SESSION_COOKIE_AGE, OCHO_HORAS)
        self.assertGreater(settings.SESSION_COOKIE_AGE, 0)

    def test_la_sesion_se_cierra_al_cerrar_el_navegador(self):
        self.assertTrue(settings.SESSION_EXPIRE_AT_BROWSER_CLOSE)

    def test_la_sesion_se_renueva_con_la_actividad(self):
        self.assertTrue(settings.SESSION_SAVE_EVERY_REQUEST)

    def test_la_cookie_de_sesion_no_la_lee_javascript_y_es_lax(self):
        self.assertTrue(settings.SESSION_COOKIE_HTTPONLY)
        self.assertEqual(settings.SESSION_COOKIE_SAMESITE, "Lax")


class VencimientoDeSesionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        grupo, _ = Group.objects.get_or_create(name="Estudiante")
        cls.usuario = User.objects.create_user("sesion_estudiante", password=CLAVE)
        cls.usuario.groups.add(grupo)

    def setUp(self):
        self.client.force_login(self.usuario)

    def _expira_en(self):
        return Session.objects.get().expire_date

    def test_con_sesion_activa_se_entra_al_panel(self):
        r = self.client.get("/estudiantes/", secure=True)
        self.assertEqual(r.status_code, 200)

    def test_la_sesion_nueva_vence_dentro_del_limite(self):
        restante = self._expira_en() - timezone.now()
        self.assertLessEqual(restante, timedelta(seconds=OCHO_HORAS))
        self.assertGreater(restante, timedelta(seconds=settings.SESSION_COOKIE_AGE - 120))

    def test_una_sesion_vencida_obliga_a_iniciar_sesion_otra_vez(self):
        Session.objects.update(expire_date=timezone.now() - timedelta(seconds=1))
        r = self.client.get("/estudiantes/", secure=True)
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login/", r["Location"])

    def test_la_actividad_renueva_el_vencimiento(self):
        Session.objects.update(expire_date=timezone.now() + timedelta(seconds=60))
        self.client.get("/estudiantes/", secure=True)
        restante = self._expira_en() - timezone.now()
        self.assertGreater(restante, timedelta(seconds=settings.SESSION_COOKIE_AGE - 120))
