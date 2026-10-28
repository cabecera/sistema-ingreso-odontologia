# Task 50 / REQ-06: control de acceso y aislamiento de datos.
from datetime import date

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from administracion.models import Especialidad
from pacientes.models import Solicitud


class MisPacientesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        grupo_estudiante, _ = Group.objects.get_or_create(name="Estudiante")
        grupo_coordinador, _ = Group.objects.get_or_create(name="Coordinador")
        grupo_super, _ = Group.objects.get_or_create(name="Super Administrador")

        # Usuarios sin contraseña: las pruebas entran con force_login.
        cls.estudiante_a = User.objects.create_user(username="estudiante_a")
        cls.estudiante_a.groups.add(grupo_estudiante)
        cls.estudiante_b = User.objects.create_user(username="estudiante_b")
        cls.estudiante_b.groups.add(grupo_estudiante)
        cls.estudiante_sin_casos = User.objects.create_user(username="estudiante_c")
        cls.estudiante_sin_casos.groups.add(grupo_estudiante)

        cls.coordinador = User.objects.create_user(username="coordinador_x")
        cls.coordinador.groups.add(grupo_coordinador)
        cls.super_admin = User.objects.create_user(username="super_admin_x")
        cls.super_admin.groups.add(grupo_super)
        cls.sin_rol = User.objects.create_user(username="sin_rol_x")
        cls.superuser = User.objects.create_superuser(
            username="superuser_x", email="su@example.com"
        )

        especialidad = Especialidad.objects.create(nombre="Especialidad de prueba 50")

        cls.paciente_a1 = cls._crear_solicitud(
            "Paciente Alfa Uno", "11111111-1", especialidad, cls.estudiante_a
        )
        cls.paciente_a2 = cls._crear_solicitud(
            "Paciente Alfa Dos", "22222222-2", especialidad, cls.estudiante_a
        )
        cls.paciente_b1 = cls._crear_solicitud(
            "Paciente Beta Uno", "33333333-3", especialidad, cls.estudiante_b
        )
        cls.paciente_sin_asignar = cls._crear_solicitud(
            "Paciente Sin Asignar", "44444444-4", especialidad, None
        )

        cls.url = reverse("estudiantes:mis_pacientes")

    @staticmethod
    def _crear_solicitud(nombre, rut, especialidad, estudiante):
        return Solicitud.objects.create(
            nombre_completo=nombre,
            fecha_nacimiento=date(1990, 1, 1),
            rut=rut,
            telefono="+56911111111",
            motivo_consulta="Consulta de prueba",
            especialidad=especialidad,
            estudiante_asignado=estudiante,
        )

    def _get(self, usuario=None):
        if usuario is not None:
            self.client.force_login(usuario)
        return self.client.get(self.url, secure=True)

    # ---------- Control de acceso (RBAC) ----------

    def test_url_publica_es_la_esperada(self):
        self.assertEqual(self.url, "/estudiantes/mis-pacientes/")

    def test_anonimo_es_redirigido_al_login(self):
        respuesta = self._get()
        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(respuesta.url.startswith("/login/"))

    def test_roles_distintos_de_estudiante_reciben_403(self):
        for usuario in (self.coordinador, self.super_admin, self.sin_rol):
            with self.subTest(usuario=usuario.username):
                self.assertEqual(self._get(usuario).status_code, 403)

    def test_estudiante_accede_con_200(self):
        self.assertEqual(self._get(self.estudiante_a).status_code, 200)

    # ---------- Aislamiento de datos ----------

    def test_estudiante_a_ve_solo_sus_pacientes(self):
        respuesta = self._get(self.estudiante_a)
        self.assertContains(respuesta, "Paciente Alfa Uno")
        self.assertContains(respuesta, "Paciente Alfa Dos")
        self.assertNotContains(respuesta, "Paciente Beta Uno")
        self.assertNotContains(respuesta, "Paciente Sin Asignar")
        self.assertEqual(
            set(respuesta.context["solicitudes"]),
            {self.paciente_a1, self.paciente_a2},
        )

    def test_estudiante_b_no_ve_pacientes_del_estudiante_a(self):
        respuesta = self._get(self.estudiante_b)
        self.assertContains(respuesta, "Paciente Beta Uno")
        self.assertNotContains(respuesta, "Paciente Alfa Uno")
        self.assertNotContains(respuesta, "Paciente Alfa Dos")
        self.assertNotContains(respuesta, "11111111-1")
        self.assertNotContains(respuesta, "22222222-2")
        self.assertEqual(
            set(respuesta.context["solicitudes"]), {self.paciente_b1}
        )

    def test_estudiante_sin_casos_ve_lista_vacia(self):
        respuesta = self._get(self.estudiante_sin_casos)
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(len(respuesta.context["solicitudes"]), 0)
        self.assertContains(respuesta, "Aún no tienes pacientes asignados")

    def test_superusuario_pasa_el_decorador_pero_no_obtiene_pacientes_ajenos(self):
        # role_required deja pasar siempre a un superusuario (diseño del
        # RBAC), pero el filtro es por request.user: su lista queda vacía.
        respuesta = self._get(self.superuser)
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(len(respuesta.context["solicitudes"]), 0)
        self.assertNotContains(respuesta, "Paciente Alfa Uno")

    def test_no_se_pueden_pedir_pacientes_ajenos_por_parametro(self):
        # Un id recibido por GET se ignora: el filtro usa la sesión.
        self.client.force_login(self.estudiante_b)
        respuesta = self.client.get(
            self.url, {"estudiante": self.estudiante_a.pk}, secure=True
        )
        self.assertNotContains(respuesta, "Paciente Alfa Uno")
        self.assertContains(respuesta, "Paciente Beta Uno")