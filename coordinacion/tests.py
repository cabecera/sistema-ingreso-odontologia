from datetime import date

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from administracion.models import Especialidad
from pacientes.models import Solicitud


# ============================================
# Tasks 47/49: Listado de solicitudes (REQ-04)
# --------------------------------------------
# Verifica dos cosas por separado:
#   1. El RBAC del listado (tarea 49): mismo patron que
#      seguridad.tests.AccesoPanelesPorRolTests, pero apuntado
#      a esta vista especifica.
#   2. El contenido/priorizacion del listado (tarea 47): que
#      solo aparezcan las solicitudes esperadas y en el orden
#      correcto (pendientes mas antiguas primero).
# ============================================
class ListadoSolicitudesRBACTests(TestCase):
    """Nadie que no sea Coordinador o Super Administrador puede ver el listado."""

    @classmethod
    def setUpTestData(cls):
        cls.url = reverse("coordinacion:listado")

        grupo_coordinador, _ = Group.objects.get_or_create(name="Coordinador")
        grupo_estudiante, _ = Group.objects.get_or_create(name="Estudiante")

        cls.coordinador = User.objects.create_user("coord_test", password="x")
        cls.coordinador.groups.add(grupo_coordinador)

        cls.estudiante = User.objects.create_user("est_test", password="x")
        cls.estudiante.groups.add(grupo_estudiante)

        cls.sin_rol = User.objects.create_user("sinrol_test", password="x")

        cls.super_admin = User.objects.create_user(
            "super_test", password="x", is_superuser=True
        )

    def test_sin_sesion_redirige_al_login(self):
        self.assertRedirects(
            self.client.get(self.url),
            f"/login/?next={self.url}",
            fetch_redirect_response=False,
        )

    def test_estudiante_recibe_403(self):
        self.client.login(username="est_test", password="x")
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_sin_rol_recibe_403(self):
        self.client.login(username="sinrol_test", password="x")
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_coordinador_accede(self):
        self.client.login(username="coord_test", password="x")
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_super_administrador_accede(self):
        self.client.login(username="super_test", password="x")
        self.assertEqual(self.client.get(self.url).status_code, 200)


class ListadoSolicitudesContenidoTests(TestCase):
    """El listado muestra lo correcto y en el orden correcto (priorización)."""

    @classmethod
    def setUpTestData(cls):
        cls.url = reverse("coordinacion:listado")

        grupo_coordinador, _ = Group.objects.get_or_create(name="Coordinador")
        cls.coordinador = User.objects.create_user("coord_contenido", password="x")
        cls.coordinador.groups.add(grupo_coordinador)

        # Nombre deliberadamente distinto al catálogo real (cargado por la
        # migración de datos de la tarea #32), que ya trae "Endodoncia" y
        # tiene nombre único: usar ese nombre aquí rompería el test contra
        # la base real de especialidades.
        cls.especialidad = Especialidad.objects.create(
            nombre="Especialidad de Prueba (tests coordinacion)", activa=True
        )

        datos_base = dict(
            fecha_nacimiento=date(1990, 1, 1),
            telefono="+56912345678",
            motivo_consulta="Dolor",
            especialidad=cls.especialidad,
        )

        # Pendiente mas antigua: debe aparecer primera en la lista de pendientes.
        cls.pendiente_antigua = Solicitud.objects.create(
            nombre_completo="Paciente Antiguo",
            rut="11111111-1",
            **datos_base,
        )
        # Pendiente mas reciente: debe aparecer despues de la antigua.
        cls.pendiente_reciente = Solicitud.objects.create(
            nombre_completo="Paciente Reciente",
            rut="22222222-2",
            **datos_base,
        )
        # Derivada: debe aparecer en la otra sección, no en pendientes.
        cls.derivada = Solicitud.objects.create(
            nombre_completo="Paciente Derivado",
            rut="33333333-3",
            estado=Solicitud.Estado.DERIVADA,
            **datos_base,
        )

    def setUp(self):
        self.client.login(username="coord_contenido", password="x")

    def test_pendientes_ordenadas_de_mas_antigua_a_mas_reciente(self):
        respuesta = self.client.get(self.url)
        pendientes = list(respuesta.context["pendientes"])
        self.assertEqual(pendientes, [self.pendiente_antigua, self.pendiente_reciente])

    def test_derivadas_no_aparecen_entre_las_pendientes(self):
        respuesta = self.client.get(self.url)
        pendientes = list(respuesta.context["pendientes"])
        self.assertNotIn(self.derivada, pendientes)

    def test_derivadas_aparecen_en_su_propia_lista(self):
        respuesta = self.client.get(self.url)
        derivadas = list(respuesta.context["derivadas"])
        self.assertEqual(derivadas, [self.derivada])

    def test_no_muestra_antecedentes_de_salud(self):
        # Minimización de datos: el listado general no debe filtrar
        # antecedentes de salud, solo datos de gestión (REQ-04 vs REQ-08).
        respuesta = self.client.get(self.url)
        contenido = respuesta.content.decode()
        self.assertNotIn("antecedentes de salud", contenido.lower())
        
class FiltrosSolicitudesCoordinacionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.url = reverse("listado_solicitudes")
        cls.coord = User.objects.get_or_create(username="coord_test", password="x")[0]
        cls.coord.groups.add(Group.objects.get_or_create(name="Coordinador")[0])
        
        # Especialidades de prueba
        cls.esp1 = Especialidad.objects.create(nombre="Endodoncia", activa=True)
        cls.esp2 = Especialidad.objects.create(nombre="Ortodoncia", activa=True)
        
        # Solicitudes de prueba con distintas fechas y especialidades
        cls.sol1 = Solicitud.objects.create(
            nombre_completo="Paciente 1",
            rut="11111111-1",
            telefono="56911111111",
            motivo_consulta="Dolor",
            especialidad=cls.esp1,
            estado=Solicitud.Estado.PENDIENTE,
            fecha_creacion="2026-05-10 10:00:00"
        )
        cls.sol2 = Solicitud.objects.create(
            nombre_completo="Paciente 2",
            rut="22222222-2",
            telefono="56922222222",
            motivo_consulta="Control",
            especialidad=cls.esp2,
            estado=Solicitud.Estado.DERIVADA,
            fecha_creacion="2026-06-15 11:00:00"
        )

    def setUp(self):
        self.client.login(username="coord_test", password="x")

    def test_filtro_por_especialidad(self):
        response = self.client.get(self.url + f'?especialidad={self.esp1.nombre}')
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.sol1, response.context['pendientes'])
        self.assertNotIn(self.sol2, response.context['derivadas'])

    def test_filtro_por_fecha(self):
        response = self.client.get(self.url + '?fecha=2026-05-10')
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.sol1, response.context['pendientes'])

    def test_filtro_por_estado(self):
        response = self.client.get(self.url + '?estado=DERIVADA')
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.sol2, response.context['derivadas'])

    def test_filtro_fecha_invalida_no_da_error_500(self):
        # Valida que ?fecha=abc devuelva status 200 y no colapse en Error 500
        response = self.client.get(self.url + '?fecha=abc')
        self.assertEqual(response.status_code, 200)
