# ============================================
# OWASP A02 (configuración) y A10 (manejo de excepciones)
# --------------------------------------------
# Cabeceras de seguridad, bloqueo de TRACE, política de contenido (CSP) sin
# scripts en línea y páginas de error propias que no muestran datos técnicos.
# Las peticiones usan secure=True (el sitio redirige HTTP a HTTPS).
# ============================================
import re

from django.conf import settings
from django.contrib.auth.models import Group, User
from django.http import HttpRequest
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.views.defaults import server_error

from seguridad.middleware import politica_csp


class CabecerasTests(TestCase):

    def test_las_paginas_llevan_csp_y_permissions_policy(self):
        r = self.client.get("/login/", secure=True)
        csp = r["Content-Security-Policy"]
        for parte in ("default-src 'self'", "frame-ancestors 'none'", "object-src 'none'",
                      "base-uri 'self'", "form-action 'self'"):
            self.assertIn(parte, csp)
        self.assertNotIn("'unsafe-inline'", csp)
        self.assertNotIn("'unsafe-eval'", csp)
        self.assertIn("camera=()", r["Permissions-Policy"])
        self.assertEqual(r["X-Frame-Options"], "DENY")
        self.assertEqual(r["X-Content-Type-Options"], "nosniff")

    def test_el_nonce_cambia_en_cada_respuesta_y_coincide_con_el_style(self):
        nonces = set()
        for _ in range(3):
            r = self.client.get("/login/", secure=True)
            nonce = re.search(r"'nonce-([^']+)'", r["Content-Security-Policy"]).group(1)
            self.assertIn(f'<style nonce="{nonce}">', r.content.decode())
            nonces.add(nonce)
        self.assertEqual(len(nonces), 3)

    def test_ninguna_pagina_tiene_scripts_ni_estilos_en_linea_sin_nonce(self):
        r = self.client.get("/login/", secure=True)
        html = r.content.decode()
        self.assertNotRegex(html, r"<script(?![^>]*\bsrc=)")           # sin <script> en línea
        self.assertNotRegex(html, r"\son[a-z]+\s*=")                    # sin onclick= etc.
        self.assertNotRegex(html, r"<[a-z]+[^>]*\sstyle=")              # sin style="..."

    def test_el_admin_de_django_lleva_una_politica_propia(self):
        r = self.client.get("/admin/login/", secure=True)
        self.assertIn("'unsafe-inline'", r["Content-Security-Policy"])
        self.assertIn("frame-ancestors 'none'", r["Content-Security-Policy"])

    def test_trace_y_track_son_rechazados(self):
        for metodo in ("TRACE", "TRACK"):
            r = self.client.generic(metodo, "/", secure=True)
            self.assertEqual(r.status_code, 405, metodo)

    def test_hsts_un_anio_sin_subdominios(self):
        with override_settings(SECURE_HSTS_SECONDS=31536000):
            r = self.client.get("/login/", secure=True)
        self.assertEqual(r["Strict-Transport-Security"], "max-age=31536000")

    def test_la_configuracion_de_produccion_activa_hsts_y_cookies_seguras(self):
        if not getattr(settings, "SECURE_SSL_REDIRECT", False):
            self.skipTest("Solo aplica con DEBUG=False (producción).")
        self.assertEqual(settings.SECURE_HSTS_SECONDS, 31536000)
        self.assertFalse(settings.SECURE_HSTS_INCLUDE_SUBDOMAINS)
        self.assertFalse(settings.SECURE_HSTS_PRELOAD)
        self.assertTrue(settings.SESSION_COOKIE_SECURE and settings.CSRF_COOKIE_SECURE)

    def test_la_politica_del_admin_es_mas_amplia_que_la_del_sitio(self):
        self.assertNotIn("'unsafe-inline'", politica_csp("abc"))
        self.assertIn("'unsafe-inline'", politica_csp("abc", es_admin=True))

    def test_un_estilo_en_linea_en_las_paginas_con_sesion_tambien_cumple_la_politica(self):
        usuario = User.objects.create_user("cab_estudiante", password="Clave-Segura#2026x")
        usuario.groups.add(Group.objects.get_or_create(name="Estudiante")[0])
        self.client.force_login(usuario)
        for ruta in ("/estudiantes/", "/estudiantes/mis-pacientes/"):
            html = self.client.get(ruta, secure=True).content.decode()
            self.assertNotRegex(html, r"<[a-z]+[^>]*\sstyle=", ruta)


class PaginasDeErrorTests(TestCase):

    def assert_sin_datos_tecnicos(self, html):
        for texto in ("Traceback", "URLconf", "DEBUG", "settings.py", "django.", "Exception"):
            self.assertNotIn(texto, html)

    def test_404_usa_la_pagina_propia(self):
        r = self.client.get("/esta-pagina-no-existe/", secure=True)
        self.assertEqual(r.status_code, 404)
        self.assertContains(r, "Página no encontrada", status_code=404)
        self.assertContains(r, "Facultad de Odontología", status_code=404)
        self.assert_sin_datos_tecnicos(r.content.decode())

    def test_500_usa_una_pagina_independiente_sin_datos_tecnicos(self):
        r = server_error(HttpRequest())
        self.assertEqual(r.status_code, 500)
        html = r.content.decode()
        self.assertIn("Error del servidor", html)
        self.assert_sin_datos_tecnicos(html)

    def test_un_error_real_en_una_vista_devuelve_500_controlado(self):
        from django.urls import path
        from django.http import HttpResponse

        def rota(request):
            raise RuntimeError("secreto-interno-123")

        class Urls:
            urlpatterns = [path("rota/", rota)]
            handler500 = "django.views.defaults.server_error"

        cliente = Client(raise_request_exception=False)
        with override_settings(ROOT_URLCONF=Urls, DEBUG=False):
            r = cliente.get("/rota/", secure=True)
        self.assertEqual(r.status_code, 500)
        self.assertNotIn("secreto-interno-123", r.content.decode())
        self.assert_sin_datos_tecnicos(r.content.decode())
        self.assertIn("Content-Security-Policy", r)

    def test_fallo_csrf_muestra_pagina_en_espanol_sin_datos_tecnicos(self):
        cliente = Client(enforce_csrf_checks=True)
        r = cliente.post("/login/", {"username": "x", "password": "y"}, secure=True)
        self.assertEqual(r.status_code, 403)
        self.assertContains(r, "Formulario expirado o no válido", status_code=403)
        self.assert_sin_datos_tecnicos(r.content.decode())

    def test_403_por_rol_usa_la_pagina_propia(self):
        usuario = User.objects.create_user("cab_paciente", password="Clave-Segura#2026x")
        usuario.groups.add(Group.objects.get_or_create(name="Paciente")[0])
        self.client.force_login(usuario)
        r = self.client.get("/coordinacion/", secure=True)
        self.assertContains(r, "Acceso denegado", status_code=403)
        self.assert_sin_datos_tecnicos(r.content.decode())

    def test_metodo_no_permitido_no_da_500(self):
        r = self.client.put("/login/", secure=True)
        self.assertLess(r.status_code, 500)
