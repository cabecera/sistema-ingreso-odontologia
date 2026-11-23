# ============================================
# Ruta configurable del sitio /admin/ (OWASP A05)
# ============================================
import importlib

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase, override_settings
from django.urls import clear_url_caches, reverse

import core.urls
from seguridad.ruta_admin import normalizar_ruta_admin


class NormalizarRutaAdminTests(TestCase):
    def test_sin_valor_se_usa_admin(self):
        for valor in (None, "", "   ", "/", "///"):
            self.assertEqual(normalizar_ruta_admin(valor), "admin/", repr(valor))

    def test_agrega_barra_final_y_quita_la_inicial(self):
        self.assertEqual(normalizar_ruta_admin("gestion-k8x2q9"), "gestion-k8x2q9/")
        self.assertEqual(normalizar_ruta_admin("/gestion-k8x2q9/"), "gestion-k8x2q9/")
        self.assertEqual(normalizar_ruta_admin("  panel/interno  "), "panel/interno/")

    def test_rechaza_caracteres_peligrosos(self):
        for valor in ("a b", "x?y=1", "../admin", "a//b", "x#y", "ñandú", "a\\b", "<script>"):
            with self.assertRaises(ImproperlyConfigured, msg=repr(valor)):
                normalizar_ruta_admin(valor)


class RutaDelAdminTests(TestCase):
    def _recargar_rutas(self):
        importlib.reload(core.urls)
        clear_url_caches()

    def test_la_ruta_del_admin_sale_de_la_configuracion(self):
        self.assertEqual(reverse("admin:index"), "/" + settings.ADMIN_URL)

    def test_con_otra_ruta_el_admin_ya_no_esta_en_admin(self):
        try:
            with override_settings(ADMIN_URL="gestion-k8x2q9/"):
                self._recargar_rutas()
                self.assertEqual(self.client.get("/admin/", secure=True).status_code, 404)
                self.assertEqual(self.client.get("/admin/login/", secure=True).status_code, 404)
                nueva = self.client.get("/gestion-k8x2q9/login/", secure=True)
                self.assertEqual(nueva.status_code, 200)
                # el admin conserva su política de cabeceras propia en la ruta nueva
                self.assertIn("'unsafe-inline'", nueva["Content-Security-Policy"])
                self.assertIn("frame-ancestors 'none'", nueva["Content-Security-Policy"])
        finally:
            self._recargar_rutas()

    def test_la_ruta_nueva_sigue_exigiendo_ser_personal_del_sitio(self):
        User.objects.create_user("sin_permisos_admin", password="ClavePrueba#2026")
        try:
            with override_settings(ADMIN_URL="gestion-k8x2q9/"):
                self._recargar_rutas()
                self.client.force_login(User.objects.get(username="sin_permisos_admin"))
                r = self.client.get("/gestion-k8x2q9/", secure=True)
                self.assertEqual(r.status_code, 302)
                self.assertIn("login", r["Location"])
        finally:
            self._recargar_rutas()
