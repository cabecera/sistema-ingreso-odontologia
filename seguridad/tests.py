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