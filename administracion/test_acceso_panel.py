# ============================================
# Task 61: Restringir el panel solo al super administrador
# Issue padre: REQ-14 (Panel de administración)
# --------------------------------------------
# Guardia de acceso del panel: recorre TODAS las rutas del namespace
# "administracion" (no una lista escrita a mano) y comprueba que solo
# el Super Administrador entra. Si alguien agrega una vista nueva a
# administracion/urls.py y olvida @role_required, estos tests fallan.
#
# También fija que el /admin/ de Django (otro panel de administración)
# no admite a Coordinador, Estudiante ni a cuentas sin rol.
# Todas las peticiones usan secure=True para no depender de DEBUG.
# ============================================

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import get_resolver, reverse

NAMESPACE = "administracion"
CLAVE = "ClavePrueba#2026"


def rutas_del_panel():
    """URLs reales de todas las rutas de administracion/urls.py.

    Las rutas con parámetros (<int:pk>) se arman con pk=1: el decorador
    actúa antes de buscar el objeto, así que el id no necesita existir.
    """
    _, resolver = get_resolver().namespace_dict[NAMESPACE]
    urls = []
    for patron in resolver.url_patterns:
        nombre = getattr(patron, "name", None)
        if not nombre:
            raise AssertionError(
                "Hay una ruta anidada o sin nombre en administracion/urls.py; "
                "este test necesita rutas con nombre para poder comprobarlas."
            )
        kwargs = {param: 1 for param in patron.pattern.converters}
        urls.append(reverse(f"{NAMESPACE}:{nombre}", kwargs=kwargs))
    return urls


class AccesoPanelAdministracionTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        grupos = {
            nombre: Group.objects.get_or_create(name=nombre)[0]
            for nombre in ("Super Administrador", "Coordinador", "Estudiante")
        }
        cls.super_admin = User.objects.create_user("acceso_superadmin", password=CLAVE)
        cls.super_admin.groups.add(grupos["Super Administrador"])
        cls.coordinador = User.objects.create_user("acceso_coordinador", password=CLAVE)
        cls.coordinador.groups.add(grupos["Coordinador"])
        cls.estudiante = User.objects.create_user("acceso_estudiante", password=CLAVE)
        cls.estudiante.groups.add(grupos["Estudiante"])
        cls.sin_rol = User.objects.create_user("acceso_sin_rol", password=CLAVE)

    def entrar_como(self, usuario):
        self.assertTrue(self.client.login(username=usuario.username, password=CLAVE))

    def test_se_estan_comprobando_todas_las_rutas_del_panel(self):
        # Evita que el recorrido quede vacío sin que nadie lo note:
        # panel, 3 de usuarios y 4 de especialidades = 8 rutas.
        self.assertGreaterEqual(len(rutas_del_panel()), 8)

    def test_anonimo_es_redirigido_al_login_en_todas_las_rutas(self):
        for url in rutas_del_panel():
            for metodo in ("get", "post"):
                with self.subTest(ruta=url, metodo=metodo):
                    respuesta = getattr(self.client, metodo)(url, secure=True)
                    self.assertEqual(respuesta.status_code, 302)
                    self.assertTrue(respuesta.url.startswith("/login/"))

    def _comprobar_403_en_todas(self, usuario):
        self.entrar_como(usuario)
        for url in rutas_del_panel():
            for metodo in ("get", "post"):
                with self.subTest(usuario=usuario.username, ruta=url, metodo=metodo):
                    respuesta = getattr(self.client, metodo)(url, secure=True)
                    self.assertEqual(respuesta.status_code, 403)

    def test_coordinador_recibe_403_en_todas_las_rutas(self):
        self._comprobar_403_en_todas(self.coordinador)

    def test_estudiante_recibe_403_en_todas_las_rutas(self):
        self._comprobar_403_en_todas(self.estudiante)

    def test_usuario_sin_rol_recibe_403_en_todas_las_rutas(self):
        self._comprobar_403_en_todas(self.sin_rol)

    def test_super_administrador_entra_al_panel_y_a_sus_listas(self):
        self.entrar_como(self.super_admin)
        for nombre in ("panel", "usuarios", "especialidades"):
            with self.subTest(ruta=nombre):
                respuesta = self.client.get(
                    reverse(f"{NAMESPACE}:{nombre}"), secure=True
                )
                self.assertEqual(respuesta.status_code, 200)

    def test_admin_de_django_no_admite_otros_roles(self):
        # /admin/ exige is_staff: ninguna de estas cuentas lo tiene, así que
        # Django las manda a su propio login en vez de mostrar el panel.
        url = reverse("admin:index")
        for usuario in (self.coordinador, self.estudiante, self.sin_rol):
            with self.subTest(usuario=usuario.username):
                self.client.logout()
                self.entrar_como(usuario)
                respuesta = self.client.get(url, secure=True)
                self.assertEqual(respuesta.status_code, 302)
                self.assertIn("login", respuesta.url)

    def test_admin_de_django_redirige_al_anonimo(self):
        respuesta = self.client.get(reverse("admin:index"), secure=True)
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn("login", respuesta.url)
