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

# ============================================
# Task 86 / REQ-18: el estudiante marca la atención como realizada
# ============================================
from django.test import Client

from seguridad.models import BitacoraAuditoria


class MarcarRealizadaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        grupo_estudiante = Group.objects.get_or_create(name="Estudiante")[0]
        cls.estudiante_a = User.objects.create_user("est_real_a")
        cls.estudiante_a.groups.add(grupo_estudiante)
        cls.estudiante_b = User.objects.create_user("est_real_b")
        cls.estudiante_b.groups.add(grupo_estudiante)
        cls.coordinador = User.objects.create_user("coord_real")
        cls.coordinador.groups.add(Group.objects.get_or_create(name="Coordinador")[0])
        cls.especialidad = Especialidad.objects.create(nombre="Especialidad de Prueba (realizada)")

    def setUp(self):
        self.solicitud = self._crear("Paciente Real Uno", "10101010-1", self.estudiante_a)
        self.url = reverse("estudiantes:marcar_realizada", args=[self.solicitud.pk])

    def _crear(self, nombre, rut, estudiante, estado=Solicitud.Estado.DERIVADA):
        return Solicitud.objects.create(
            nombre_completo=nombre,
            rut=rut,
            fecha_nacimiento=date(1990, 1, 1),
            telefono="+56912345678",
            motivo_consulta="Dolor",
            especialidad=self.especialidad,
            estudiante_asignado=estudiante,
            estado=estado,
        )

    def _post(self, usuario, url=None):
        self.client.force_login(usuario)
        return self.client.post(url or self.url, secure=True)

    def _estado(self):
        self.solicitud.refresh_from_db()
        return self.solicitud.estado

    def test_el_estudiante_asignado_marca_realizada_y_queda_en_la_bitacora(self):
        respuesta = self._post(self.estudiante_a)
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(self._estado(), Solicitud.Estado.REALIZADO)
        registro = BitacoraAuditoria.objects.get(accion="Atención realizada")
        self.assertEqual(registro.usuario, self.estudiante_a)
        self.assertIn(f"#{self.solicitud.pk}", registro.detalles)

    def test_un_estudiante_no_puede_marcar_el_paciente_de_otro(self):
        respuesta = self._post(self.estudiante_b)
        self.assertEqual(respuesta.status_code, 404)
        self.assertEqual(self._estado(), Solicitud.Estado.DERIVADA)
        self.assertEqual(BitacoraAuditoria.objects.count(), 0)

    def test_no_se_puede_saltar_ni_repetir_la_transicion(self):
        for estado in (
            Solicitud.Estado.PENDIENTE,
            Solicitud.Estado.REALIZADO,
            Solicitud.Estado.TERMINADO,
        ):
            with self.subTest(estado=estado):
                self.solicitud.estado = estado
                self.solicitud.save(update_fields=["estado"])
                self._post(self.estudiante_a)
                self.assertEqual(self._estado(), estado)
        self.assertEqual(BitacoraAuditoria.objects.count(), 0)

    def test_acceso_por_rol_y_metodo(self):
        anonimo = self.client.post(self.url, secure=True)
        self.assertEqual(anonimo.status_code, 302)
        self.assertTrue(anonimo.url.startswith("/login/"))
        self.assertEqual(self._post(self.coordinador).status_code, 403)
        self.client.force_login(self.estudiante_a)
        self.assertEqual(self.client.get(self.url, secure=True).status_code, 405)
        self.assertEqual(self._estado(), Solicitud.Estado.DERIVADA)

    def test_post_sin_token_csrf_es_rechazado(self):
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.estudiante_a)
        self.assertEqual(cliente.post(self.url, secure=True).status_code, 403)
        self.assertEqual(self._estado(), Solicitud.Estado.DERIVADA)

    def test_solicitud_inexistente_devuelve_404(self):
        url = reverse("estudiantes:marcar_realizada", args=[999999])
        self.assertEqual(self._post(self.estudiante_a, url).status_code, 404)

    def test_mis_pacientes_muestra_el_boton_solo_para_las_derivadas(self):
        otra = self._crear("Paciente Ya Realizado", "20202020-2", self.estudiante_a, Solicitud.Estado.REALIZADO)
        self.client.force_login(self.estudiante_a)
        respuesta = self.client.get(reverse("estudiantes:mis_pacientes"), secure=True)
        self.assertContains(respuesta, f'action="{self.url}"')
        self.assertNotContains(
            respuesta, reverse("estudiantes:marcar_realizada", args=[otra.pk])
        )
        self.assertContains(respuesta, "Realizado")
