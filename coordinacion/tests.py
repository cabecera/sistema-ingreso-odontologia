from datetime import date, datetime

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

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


# ============================================
# Task 48: Filtros de búsqueda del listado (REQ-04)
# --------------------------------------------
# Los filtros llegan por GET, o sea, los controla el usuario (aunque
# el formulario solo envíe valores válidos, cualquiera puede editar la
# URL o usar curl). Se prueba que filtren bien y que los valores
# inválidos o maliciosos NUNCA rompan el listado (sin error 500).
# ============================================
class ListadoFiltrosTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.url = reverse("coordinacion:listado")

        grupo_coordinador, _ = Group.objects.get_or_create(name="Coordinador")
        cls.coordinador = User.objects.create_user("coord_filtros", password="x")
        cls.coordinador.groups.add(grupo_coordinador)

        cls.esp_a = Especialidad.objects.create(nombre="Esp A (tests filtros)")
        cls.esp_b = Especialidad.objects.create(nombre="Esp B (tests filtros)")

        def crear(nombre, rut, esp, estado=Solicitud.Estado.PENDIENTE):
            return Solicitud.objects.create(
                nombre_completo=nombre,
                rut=rut,
                fecha_nacimiento=date(1990, 1, 1),
                telefono="+56912345678",
                motivo_consulta="Dolor",
                especialidad=esp,
                estado=estado,
            )

        cls.a_pendiente = crear("Pendiente EspA", "11111111-1", cls.esp_a)
        cls.b_pendiente = crear("Pendiente EspB", "22222222-2", cls.esp_b)
        cls.a_derivada = crear(
            "Derivada EspA", "33333333-3", cls.esp_a, Solicitud.Estado.DERIVADA
        )

        # fecha_creacion es auto_now_add: se fija con update() para controlarla.
        # 15:00 UTC = 11:00/12:00 en Chile, o sea, el mismo día calendario local.
        zona = timezone.get_current_timezone()
        cls.dia_antiguo = date(2026, 3, 10)
        cls.dia_reciente = date(2026, 4, 20)
        Solicitud.objects.filter(pk=cls.a_pendiente.pk).update(
            fecha_creacion=timezone.make_aware(datetime(2026, 3, 10, 12, 0), zona)
        )
        Solicitud.objects.filter(
            pk__in=[cls.b_pendiente.pk, cls.a_derivada.pk]
        ).update(
            fecha_creacion=timezone.make_aware(datetime(2026, 4, 20, 12, 0), zona)
        )

    def setUp(self):
        self.client.force_login(self.coordinador)

    def _get(self, **params):
        return self.client.get(self.url, params, secure=True)

    def _nombres(self, respuesta):
        return {
            s.nombre_completo
            for s in list(respuesta.context["pendientes"])
            + list(respuesta.context["derivadas"])
        }

    # ---------- Filtros que funcionan ----------

    def test_sin_filtros_muestra_todo(self):
        respuesta = self._get()
        self.assertEqual(
            self._nombres(respuesta),
            {"Pendiente EspA", "Pendiente EspB", "Derivada EspA"},
        )

    def test_filtra_por_especialidad(self):
        respuesta = self._get(especialidad=self.esp_a.pk)
        self.assertEqual(self._nombres(respuesta), {"Pendiente EspA", "Derivada EspA"})

    def test_filtra_por_fecha(self):
        respuesta = self._get(fecha=self.dia_antiguo.isoformat())
        self.assertEqual(self._nombres(respuesta), {"Pendiente EspA"})

    def test_filtra_por_estado_pendiente(self):
        respuesta = self._get(estado="PENDIENTE")
        self.assertEqual(self._nombres(respuesta), {"Pendiente EspA", "Pendiente EspB"})
        self.assertNotContains(respuesta, "Derivada EspA")

    def test_filtra_por_estado_derivada(self):
        respuesta = self._get(estado="DERIVADA")
        self.assertEqual(self._nombres(respuesta), {"Derivada EspA"})

    def test_filtros_combinados(self):
        respuesta = self._get(
            especialidad=self.esp_a.pk,
            fecha=self.dia_reciente.isoformat(),
            estado="DERIVADA",
        )
        self.assertEqual(self._nombres(respuesta), {"Derivada EspA"})

    def test_la_priorizacion_se_mantiene_con_filtros(self):
        # Filtrar no debe alterar el orden de las pendientes (REQ-04).
        respuesta = self._get(estado="PENDIENTE")
        self.assertEqual(
            list(respuesta.context["pendientes"]),
            [self.a_pendiente, self.b_pendiente],
        )

    def test_filtro_sin_resultados_muestra_mensaje(self):
        respuesta = self._get(fecha="2020-01-01")
        self.assertEqual(self._nombres(respuesta), set())
        self.assertContains(respuesta, "coincide con los filtros")

    # ---------- Entradas inválidas o maliciosas ----------

    def test_fecha_invalida_no_rompe_el_listado(self):
        respuesta = self._get(fecha="abc")
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.context["fecha_invalida"])
        self.assertContains(respuesta, "La fecha ingresada no es válida")
        # El filtro se ignora: se ve todo, y el texto recibido no se refleja.
        self.assertEqual(len(self._nombres(respuesta)), 3)
        self.assertNotContains(respuesta, 'value="abc"')

    def test_fechas_en_los_limites_no_rompen_el_listado(self):
        for valor in ("9999-12-31", "0001-01-01", "2026-02-30", "2026-13-01"):
            with self.subTest(fecha=valor):
                self.assertEqual(self._get(fecha=valor).status_code, 200)

    def test_especialidad_invalida_se_ignora(self):
        for valor in ("abc", "999999", "-1", "1; DROP TABLE x", "9" * 40, "²"):
            with self.subTest(especialidad=valor):
                respuesta = self._get(especialidad=valor)
                self.assertEqual(respuesta.status_code, 200)
                self.assertEqual(len(self._nombres(respuesta)), 3)

    def test_estado_invalido_se_ignora(self):
        for valor in ("HACKEADO", "' OR '1'='1", "pendiente"):
            with self.subTest(estado=valor):
                respuesta = self._get(estado=valor)
                self.assertEqual(respuesta.status_code, 200)
                self.assertEqual(len(self._nombres(respuesta)), 3)

    def test_script_en_los_parametros_no_se_refleja(self):
        payload = "<script>alert(1)</script>"
        respuesta = self._get(fecha=payload, estado=payload, especialidad=payload)
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotContains(respuesta, payload)

    # ---------- Los filtros no saltan el RBAC ----------

    def test_estudiante_sigue_recibiendo_403_con_filtros(self):
        grupo_estudiante, _ = Group.objects.get_or_create(name="Estudiante")
        estudiante = User.objects.create_user("est_filtros", password="x")
        estudiante.groups.add(grupo_estudiante)
        self.client.force_login(estudiante)
        self.assertEqual(self._get(estado="PENDIENTE").status_code, 403)
