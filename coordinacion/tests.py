from datetime import date, datetime, timedelta

from django.contrib.auth.models import Group, User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from administracion.models import Especialidad
from pacientes.models import Solicitud
from seguridad.models import BitacoraAuditoria


def horario_futuro(dias=3):
    """Valor válido para <input type=datetime-local> (hora local, futura)."""
    return (timezone.localtime() + timedelta(days=dias)).strftime("%Y-%m-%dT%H:%M")


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
        cls.url = reverse("coordinacion:listado_solicitudes")

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
            self.client.get(self.url, secure=True),
            f"/login/?next={self.url}",
            fetch_redirect_response=False,
        )

    def test_estudiante_recibe_403(self):
        self.client.login(username="est_test", password="x")
        self.assertEqual(self.client.get(self.url, secure=True).status_code, 403)

    def test_sin_rol_recibe_403(self):
        self.client.login(username="sinrol_test", password="x")
        self.assertEqual(self.client.get(self.url, secure=True).status_code, 403)

    def test_coordinador_accede(self):
        self.client.login(username="coord_test", password="x")
        self.assertEqual(self.client.get(self.url, secure=True).status_code, 200)

    def test_super_administrador_accede(self):
        self.client.login(username="super_test", password="x")
        self.assertEqual(self.client.get(self.url, secure=True).status_code, 200)


class ListadoSolicitudesContenidoTests(TestCase):
    """El listado muestra lo correcto y en el orden correcto (priorización)."""

    @classmethod
    def setUpTestData(cls):
        cls.url = reverse("coordinacion:listado_solicitudes")

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
        respuesta = self.client.get(self.url, secure=True)
        pendientes = list(respuesta.context["pendientes"])
        self.assertEqual(pendientes, [self.pendiente_antigua, self.pendiente_reciente])

    def test_derivadas_no_aparecen_entre_las_pendientes(self):
        respuesta = self.client.get(self.url, secure=True)
        pendientes = list(respuesta.context["pendientes"])
        self.assertNotIn(self.derivada, pendientes)

    def test_derivadas_aparecen_en_su_propia_lista(self):
        respuesta = self.client.get(self.url, secure=True)
        derivadas = list(respuesta.context["derivadas"])
        self.assertEqual(derivadas, [self.derivada])

    def test_no_muestra_antecedentes_de_salud(self):
        # Minimización de datos: el listado general no debe filtrar
        # antecedentes de salud, solo datos de gestión (REQ-04 vs REQ-08).
        respuesta = self.client.get(self.url, secure=True)
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
        cls.url = reverse("coordinacion:listado_solicitudes")

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


class DerivarSolicitudTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        grupo_coordinador, _ = Group.objects.get_or_create(name="Coordinador")
        grupo_estudiante, _ = Group.objects.get_or_create(name="Estudiante")

        cls.coordinador = User.objects.create_user("coord_derivar")
        cls.coordinador.groups.add(grupo_coordinador)

        cls.estudiante = User.objects.create_user("est_derivar")
        cls.estudiante.groups.add(grupo_estudiante)

        cls.otro_usuario = User.objects.create_user("usuario_no_estudiante")
        cls.especialidad = Especialidad.objects.create(
            nombre="Especialidad de Prueba (derivación)"
        )
        cls.solicitud = Solicitud.objects.create(
            nombre_completo="Paciente de Prueba",
            rut="44444444-4",
            fecha_nacimiento=date(1990, 1, 1),
            telefono="+56912345678",
            motivo_consulta="Dolor",
            especialidad=cls.especialidad,
        )

    def setUp(self):
        self.client.force_login(self.coordinador)
        self.url = reverse(
            "coordinacion:derivar_solicitud",
            args=[self.solicitud.pk],
        )

    def test_deriva_y_guarda_estudiante_responsable_y_fecha(self):
        respuesta = self.client.post(
            self.url,
            {"estudiante_asignado": str(self.estudiante.pk), "fecha_atencion": horario_futuro()},
            secure=True,
        )

        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(
            respuesta["Location"],
            reverse("coordinacion:listado_solicitudes"),
        )
        self.solicitud.refresh_from_db()
        self.assertEqual(self.solicitud.estudiante_asignado, self.estudiante)
        self.assertEqual(self.solicitud.derivado_por, self.coordinador)
        self.assertIsNotNone(self.solicitud.fecha_derivacion)
        self.assertEqual(self.solicitud.estado, Solicitud.Estado.DERIVADA)

    def test_rechaza_usuario_que_no_es_estudiante(self):
        respuesta = self.client.post(
            self.url,
            {"estudiante_asignado": str(self.otro_usuario.pk)},
            secure=True,
        )

        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(
            respuesta["Location"],
            reverse("coordinacion:listado_solicitudes"),
        )
        self.solicitud.refresh_from_db()
        self.assertIsNone(self.solicitud.estudiante_asignado)
        self.assertIsNone(self.solicitud.derivado_por)
        self.assertIsNone(self.solicitud.fecha_derivacion)
        self.assertEqual(self.solicitud.estado, Solicitud.Estado.PENDIENTE)

    def test_rechaza_identificador_invalido(self):
        respuesta = self.client.post(
            self.url,
            {"estudiante_asignado": "no-es-un-id"},
            secure=True,
        )

        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(
            respuesta["Location"],
            reverse("coordinacion:listado_solicitudes"),
        )
        self.solicitud.refresh_from_db()
        self.assertIsNone(self.solicitud.estudiante_asignado)

    def test_solo_acepta_post(self):
        self.assertEqual(self.client.get(self.url, secure=True).status_code, 405)


# ============================================
# Task 54: registro automático de auditoría al derivar
# --------------------------------------------
# Cada derivación exitosa deja una fila en BitacoraAuditoria; los
# intentos rechazados no dejan nada. Además se prueba el RBAC de la
# acción, la protección CSRF y que el listado ofrezca un formulario POST.
# ============================================
class AuditoriaDerivacionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        grupo_coordinador, _ = Group.objects.get_or_create(name="Coordinador")
        grupo_estudiante, _ = Group.objects.get_or_create(name="Estudiante")

        cls.coordinador = User.objects.create_user("coord_auditoria")
        cls.coordinador.groups.add(grupo_coordinador)
        cls.estudiante = User.objects.create_user("est_auditoria")
        cls.estudiante.groups.add(grupo_estudiante)
        cls.estudiante_inactivo = User.objects.create_user(
            "est_inactivo", is_active=False
        )
        cls.estudiante_inactivo.groups.add(grupo_estudiante)
        cls.sin_rol = User.objects.create_user("sinrol_auditoria")

        especialidad = Especialidad.objects.create(
            nombre="Especialidad de Prueba (auditoría)"
        )
        cls.solicitud = Solicitud.objects.create(
            nombre_completo="Paciente Auditado Uno",
            rut="55555555-5",
            fecha_nacimiento=date(1990, 1, 1),
            telefono="+56912345678",
            motivo_consulta="Dolor",
            especialidad=especialidad,
        )
        cls.url = reverse("coordinacion:derivar_solicitud", args=[cls.solicitud.pk])

    def _derivar(self, usuario, estudiante, cliente=None):
        cliente = cliente or self.client
        cliente.force_login(usuario)
        return cliente.post(
            self.url,
            {"estudiante_asignado": str(estudiante.pk), "fecha_atencion": horario_futuro()},
            secure=True,
        )

    # ---------- Bitácora ----------

    def test_derivacion_exitosa_deja_un_registro_en_la_bitacora(self):
        self._derivar(self.coordinador, self.estudiante)
        self.assertEqual(BitacoraAuditoria.objects.count(), 1)
        registro = BitacoraAuditoria.objects.get()
        self.assertEqual(registro.usuario, self.coordinador)
        self.assertEqual(registro.accion, "Derivación de solicitud")
        self.assertIn(f"#{self.solicitud.pk}", registro.detalles)
        self.assertIn(self.estudiante.username, registro.detalles)
        self.assertIsNotNone(registro.fecha_hora)

    def test_la_bitacora_no_guarda_datos_del_paciente(self):
        self._derivar(self.coordinador, self.estudiante)
        detalles = BitacoraAuditoria.objects.get().detalles
        self.assertNotIn("Paciente Auditado Uno", detalles)
        self.assertNotIn("55555555", detalles)

    def test_derivacion_rechazada_no_deja_registro(self):
        self._derivar(self.coordinador, self.sin_rol)
        self.assertEqual(BitacoraAuditoria.objects.count(), 0)

    def test_estudiante_inactivo_no_puede_recibir_derivaciones(self):
        self._derivar(self.coordinador, self.estudiante_inactivo)
        self.solicitud.refresh_from_db()
        self.assertEqual(self.solicitud.estado, Solicitud.Estado.PENDIENTE)
        self.assertEqual(BitacoraAuditoria.objects.count(), 0)

    def test_no_se_puede_derivar_dos_veces(self):
        self._derivar(self.coordinador, self.estudiante)
        otro = User.objects.create_user("otro_est")
        otro.groups.add(Group.objects.get(name="Estudiante"))
        self._derivar(self.coordinador, otro)
        self.solicitud.refresh_from_db()
        self.assertEqual(self.solicitud.estudiante_asignado, self.estudiante)
        self.assertEqual(BitacoraAuditoria.objects.count(), 1)

    def test_solicitud_inexistente_devuelve_404(self):
        self.client.force_login(self.coordinador)
        url = reverse("coordinacion:derivar_solicitud", args=[999999])
        respuesta = self.client.post(
            url, {"estudiante_asignado": str(self.estudiante.pk)}, secure=True
        )
        self.assertEqual(respuesta.status_code, 404)
        self.assertEqual(BitacoraAuditoria.objects.count(), 0)

    # ---------- RBAC y CSRF de la acción ----------

    def test_anonimo_es_redirigido_al_login_y_no_deriva(self):
        respuesta = self.client.post(
            self.url, {"estudiante_asignado": str(self.estudiante.pk)}, secure=True
        )
        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(respuesta.url.startswith("/login/"))
        self.solicitud.refresh_from_db()
        self.assertEqual(self.solicitud.estado, Solicitud.Estado.PENDIENTE)

    def test_estudiante_recibe_403_y_no_deriva(self):
        respuesta = self._derivar(self.estudiante, self.estudiante)
        self.assertEqual(respuesta.status_code, 403)
        self.solicitud.refresh_from_db()
        self.assertEqual(self.solicitud.estado, Solicitud.Estado.PENDIENTE)
        self.assertEqual(BitacoraAuditoria.objects.count(), 0)

    def test_post_sin_token_csrf_es_rechazado(self):
        cliente = Client(enforce_csrf_checks=True)
        respuesta = self._derivar(self.coordinador, self.estudiante, cliente)
        self.assertEqual(respuesta.status_code, 403)
        self.solicitud.refresh_from_db()
        self.assertEqual(self.solicitud.estado, Solicitud.Estado.PENDIENTE)

    # ---------- Listado ----------

    def test_listado_ofrece_formulario_post_con_estudiantes_activos(self):
        self.client.force_login(self.coordinador)
        respuesta = self.client.get(
            reverse("coordinacion:listado_solicitudes"), secure=True
        )
        self.assertContains(respuesta, f'action="{self.url}"')
        self.assertContains(respuesta, "csrfmiddlewaretoken")
        self.assertContains(respuesta, "est_auditoria")
        self.assertNotContains(respuesta, "est_inactivo")
        # El botón ya no es un enlace GET.
        self.assertNotContains(respuesta, f'href="{self.url}"')

    def test_listado_muestra_quien_derivo_y_cuando(self):
        self._derivar(self.coordinador, self.estudiante)
        respuesta = self.client.get(
            reverse("coordinacion:listado_solicitudes"), secure=True
        )
        self.assertContains(respuesta, "coord_auditoria")
        self.assertContains(respuesta, "Derivada por")


# ============================================
# Task 86 / REQ-18: horario de atención y estados nuevos
# ============================================
class HorarioAtencionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.coordinador = User.objects.create_user("coord_horario")
        cls.coordinador.groups.add(Group.objects.get_or_create(name="Coordinador")[0])
        cls.estudiante = User.objects.create_user("est_horario")
        cls.estudiante.groups.add(Group.objects.get_or_create(name="Estudiante")[0])
        cls.especialidad = Especialidad.objects.create(nombre="Especialidad de Prueba (horario)")

    def setUp(self):
        self.client.force_login(self.coordinador)
        self.solicitud = self._crear("Paciente Horario Uno", "99999999-9")
        self.url = reverse("coordinacion:derivar_solicitud", args=[self.solicitud.pk])

    def _crear(self, nombre, rut, estado=Solicitud.Estado.PENDIENTE, **extra):
        return Solicitud.objects.create(
            nombre_completo=nombre,
            rut=rut,
            fecha_nacimiento=date(1990, 1, 1),
            telefono="+56912345678",
            motivo_consulta="Dolor",
            especialidad=self.especialidad,
            estado=estado,
            **extra,
        )

    def _derivar(self, fecha):
        return self.client.post(
            self.url,
            {"estudiante_asignado": str(self.estudiante.pk), "fecha_atencion": fecha},
            secure=True,
        )

    def _sin_cambios(self):
        self.solicitud.refresh_from_db()
        self.assertEqual(self.solicitud.estado, Solicitud.Estado.PENDIENTE)
        self.assertIsNone(self.solicitud.fecha_atencion)
        self.assertEqual(BitacoraAuditoria.objects.count(), 0)

    # ---------- Fecha válida ----------

    def test_deriva_y_guarda_el_horario_en_hora_local(self):
        fecha = horario_futuro(5)
        self._derivar(fecha)
        self.solicitud.refresh_from_db()
        self.assertEqual(self.solicitud.estado, Solicitud.Estado.DERIVADA)
        self.assertEqual(
            timezone.localtime(self.solicitud.fecha_atencion).strftime("%Y-%m-%dT%H:%M"),
            fecha,
        )

    def test_la_bitacora_registra_el_horario(self):
        fecha = horario_futuro(2)
        self._derivar(fecha)
        detalles = BitacoraAuditoria.objects.get().detalles
        esperado = datetime.strptime(fecha, "%Y-%m-%dT%H:%M").strftime("%d-%m-%Y %H:%M")
        self.assertIn(esperado, detalles)

    # ---------- Fecha inválida ----------

    def test_rechaza_fechas_invalidas(self):
        ahora = timezone.localtime()
        invalidas = {
            "vacía": "",
            "pasada": (ahora - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M"),
            "justo ahora": (ahora - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M"),
            "más de un año": (ahora + timedelta(days=400)).strftime("%Y-%m-%dT%H:%M"),
            "texto": "mañana temprano",
            "sql": "2026-01-01'; DROP TABLE x; --",
            "con zona horaria": "2030-01-01T10:00+00:00",
            "fecha imposible": "2026-02-31T10:00",
            "año enorme": "9999-12-31T23:59",
        }
        for nombre, valor in invalidas.items():
            with self.subTest(caso=nombre):
                respuesta = self._derivar(valor)
                self.assertEqual(respuesta.status_code, 302)
                self._sin_cambios()

    def test_sin_el_campo_de_fecha_no_deriva(self):
        respuesta = self.client.post(
            self.url, {"estudiante_asignado": str(self.estudiante.pk)}, secure=True
        )
        self.assertEqual(respuesta.status_code, 302)
        self._sin_cambios()

    # ---------- Transiciones ----------

    def test_no_se_deriva_una_solicitud_ya_realizada_o_terminada(self):
        for estado in (Solicitud.Estado.REALIZADO, Solicitud.Estado.TERMINADO):
            with self.subTest(estado=estado):
                otra = self._crear(f"Otra {estado}", "11111111-1", estado=estado)
                url = reverse("coordinacion:derivar_solicitud", args=[otra.pk])
                self.client.post(
                    url,
                    {"estudiante_asignado": str(self.estudiante.pk), "fecha_atencion": horario_futuro()},
                    secure=True,
                )
                otra.refresh_from_db()
                self.assertEqual(otra.estado, estado)
                self.assertIsNone(otra.estudiante_asignado)

    # ---------- Listado ----------

    def test_listado_ofrece_selector_de_horario_con_minimo(self):
        respuesta = self.client.get(reverse("coordinacion:listado_solicitudes"), secure=True)
        self.assertContains(respuesta, 'type="datetime-local"')
        self.assertContains(respuesta, f'min="{respuesta.context["min_atencion"]}"')

    def test_listado_muestra_el_horario_de_las_derivadas(self):
        self._derivar(horario_futuro(4))
        respuesta = self.client.get(reverse("coordinacion:listado_solicitudes"), secure=True)
        self.assertContains(respuesta, "Horario de atención")
        derivada = respuesta.context["derivadas"][0]
        self.assertIsNotNone(derivada.fecha_atencion)

    def test_realizadas_y_terminadas_siguen_visibles_en_el_listado(self):
        self._crear("Paciente Realizado", "22222222-2", Solicitud.Estado.REALIZADO)
        self._crear("Paciente Terminado", "33333333-3", Solicitud.Estado.TERMINADO)
        url = reverse("coordinacion:listado_solicitudes")
        respuesta = self.client.get(url, secure=True)
        self.assertContains(respuesta, "Paciente Realizado")
        self.assertContains(respuesta, "Paciente Terminado")
        self.assertEqual(len(respuesta.context["atendidas"]), 2)

    def test_filtro_por_estado_realizado_oculta_las_otras_secciones(self):
        self._crear("Paciente Realizado", "22222222-2", Solicitud.Estado.REALIZADO)
        url = reverse("coordinacion:listado_solicitudes")
        respuesta = self.client.get(url, {"estado": "REALIZADO"}, secure=True)
        self.assertContains(respuesta, "Paciente Realizado")
        self.assertNotContains(respuesta, "Paciente Horario Uno")
        self.assertNotContains(respuesta, "Pendientes (")
