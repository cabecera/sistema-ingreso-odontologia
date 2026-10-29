# ============================================
# Follow-up Task 35 (Issue GitHub #16)
# Tests del decorador role_required, cubriendo los 4 casos
# descritos en su docstring.
# ============================================

from django.contrib.auth.models import Group, User
from django.http import HttpResponse
from django.test import RequestFactory, TestCase

from seguridad.decorators import role_required


@role_required("Coordinador")
def vista_de_prueba(request):
    return HttpResponse("ok")


class RoleRequiredTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.grupo_coordinador, _ = Group.objects.get_or_create(name="Coordinador")
        self.grupo_estudiante, _ = Group.objects.get_or_create(name="Estudiante")

    def _request_con_usuario(self, usuario):
        request = self.factory.get("/vista-de-prueba/")
        request.user = usuario
        return request

    def test_usuario_anonimo_es_redirigido_al_login(self):
        # login_required debe actuar antes que la verificación de rol.
        from django.contrib.auth.models import AnonymousUser

        request = self._request_con_usuario(AnonymousUser())
        response = vista_de_prueba(request)
        self.assertEqual(response.status_code, 302)  # redirección a LOGIN_URL

    def test_usuario_autenticado_sin_grupos_recibe_403(self):
        usuario = User.objects.create_user(username="sin_rol", password="x")
        request = self._request_con_usuario(usuario)
        with self.assertRaises(Exception):  # PermissionDenied -> 403
            vista_de_prueba(request)

    def test_usuario_con_rol_correcto_accede(self):
        usuario = User.objects.create_user(username="coordinador1", password="x")
        usuario.groups.add(self.grupo_coordinador)
        request = self._request_con_usuario(usuario)
        response = vista_de_prueba(request)
        self.assertEqual(response.status_code, 200)

    def test_usuario_con_rol_incorrecto_recibe_403(self):
        usuario = User.objects.create_user(username="estudiante1", password="x")
        usuario.groups.add(self.grupo_estudiante)
        request = self._request_con_usuario(usuario)
        with self.assertRaises(Exception):
            vista_de_prueba(request)

    def test_superusuario_accede_sin_pertenecer_a_ningun_grupo(self):
        usuario = User.objects.create_superuser(
            username="admin_test", password="x", email="a@a.com"
        )
        request = self._request_con_usuario(usuario)
        response = vista_de_prueba(request)
        self.assertEqual(response.status_code, 200)


# ============================================
# Tests de acceso HTTP a los paneles reales
# (/administracion/, /coordinacion/, /estudiantes/)
# y al formulario público (/). Complementan los
# tests unitarios del decorador de arriba.
# ============================================
class AccesoPanelesPorRolTests(TestCase):
    RUTAS = ["/administracion/", "/coordinacion/", "/estudiantes/"]

    def setUp(self):
        self.grupo_super, _ = Group.objects.get_or_create(name="Super Administrador")
        self.grupo_coordinador, _ = Group.objects.get_or_create(name="Coordinador")
        self.grupo_estudiante, _ = Group.objects.get_or_create(name="Estudiante")

        self.sin_rol = User.objects.create_user(username="sin_rol_panel", password="x")

        self.estudiante = User.objects.create_user(
            username="estudiante_panel", password="x"
        )
        self.estudiante.groups.add(self.grupo_estudiante)

        self.coordinador = User.objects.create_user(
            username="coordinador_panel", password="x"
        )
        self.coordinador.groups.add(self.grupo_coordinador)

        self.super_admin = User.objects.create_user(
            username="super_admin_panel", password="x"
        )
        self.super_admin.groups.add(self.grupo_super)

        self.superuser = User.objects.create_superuser(
            username="superuser_panel",
            password="x",
            email="su@example.com",
        )

    def _codigos(self, usuario):
        self.client.force_login(usuario)
        return [self.client.get(ruta).status_code for ruta in self.RUTAS]

    def test_sin_sesion_redirige_al_login(self):
        for ruta in self.RUTAS:
            with self.subTest(ruta=ruta):
                self.assertRedirects(
                    self.client.get(ruta),
                    f"/login/?next={ruta}",
                    fetch_redirect_response=False,
                )

    def test_sin_rol_recibe_403(self):
        self.assertEqual(self._codigos(self.sin_rol), [403, 403, 403])

    def test_estudiante_solo_accede_a_estudiantes(self):
        self.assertEqual(self._codigos(self.estudiante), [403, 403, 200])

    def test_coordinador_accede_coordinacion_y_estudiantes(self):
        self.assertEqual(self._codigos(self.coordinador), [403, 200, 200])

    def test_super_administrador_accede_a_los_tres_paneles(self):
        self.assertEqual(self._codigos(self.super_admin), [200, 200, 200])

    def test_superusuario_accede_a_los_tres_paneles(self):
        self.assertEqual(self._codigos(self.superuser), [200, 200, 200])

    def test_formulario_publico_responde_200(self):
        respuesta = self.client.get("/")
        self.assertEqual(respuesta.status_code, 200)



# ============================================
# Página 403 personalizada
# Issue padre: REQ-07 (Control de acceso basado en roles)
# ============================================
class PaginaAccesoDenegadoTests(TestCase):
    def setUp(self):
        grupo_estudiante, _ = Group.objects.get_or_create(name="Estudiante")
        self.estudiante = User.objects.create_user(username="estudiante_403")
        self.estudiante.groups.add(grupo_estudiante)
        self.client.force_login(self.estudiante)

    def test_403_usa_el_template_personalizado(self):
        respuesta = self.client.get("/coordinacion/", secure=True)
        self.assertEqual(respuesta.status_code, 403)
        self.assertTemplateUsed(respuesta, "403.html")
        self.assertContains(respuesta, "Acceso denegado", status_code=403)

    def test_403_mantiene_el_menu_y_ofrece_volver_al_inicio(self):
        respuesta = self.client.get("/administracion/", secure=True)
        self.assertContains(respuesta, "Cerrar sesión", status_code=403)
        self.assertContains(respuesta, "Volver al inicio", status_code=403)

    def test_403_no_filtra_detalles_internos(self):
        contenido = self.client.get("/coordinacion/", secure=True).content.decode()
        for texto in ("Traceback", "PermissionDenied", "role_required"):
            with self.subTest(texto=texto):
                self.assertNotIn(texto, contenido)