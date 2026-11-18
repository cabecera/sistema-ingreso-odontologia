# ============================================
# Task 56: Revisar que ninguna consulta a la base de datos sea insegura
# Issue padre: REQ-10 (Validación y sanitización de entradas)
# --------------------------------------------
# Confirma que el sistema no permite inyectar código a través de los
# formularios ni de los parámetros de la URL. Son cuatro familias:
#   1. Inyección SQL en el formulario público y en el login.
#   2. Inyección SQL en parámetros GET (filtros) y POST (derivación).
#   3. XSS almacenado: un texto con <script> se muestra escapado.
#   4. Guardia estática: falla el CI si alguien agrega SQL crudo,
#      |safe, mark_safe o csrf_exempt (shift-left: se detecta en el push).
# Django protege con el ORM (consultas parametrizadas) y el
# autoescape de las plantillas; estas pruebas fijan que nadie lo
# desactive sin que el pipeline se ponga en rojo.
# ============================================

import re
from datetime import date
from pathlib import Path

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from administracion.models import Especialidad
from pacientes.models import Solicitud

PAYLOADS_SQL = [
    "' OR '1'='1",
    "'; DROP TABLE pacientes_solicitud; --",
    "1 OR 1=1",
    "1; DELETE FROM auth_user",
    '" OR ""="',
    "1 UNION SELECT username, password FROM auth_user",
]


class InyeccionFormularioPublicoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.especialidad = Especialidad.objects.create(
            nombre="Especialidad de Prueba (inyección)", activa=True
        )

    def datos(self, **cambios):
        base = {
            "nombre_completo": "Ana Torres",
            "fecha_nacimiento": "1990-01-01",
            "rut": "12.345.678-5",
            "telefono": "+56 9 1234 5678",
            "especialidad": self.especialidad.pk,
            "motivo_consulta": "Dolor de muelas hace una semana",
        }
        base.update(cambios)
        return base

    def test_campos_estructurados_rechazan_payloads_sql(self):
        # Nombre, RUT y teléfono tienen formato propio: el payload se rechaza.
        for campo in ("nombre_completo", "rut", "telefono"):
            for payload in PAYLOADS_SQL:
                with self.subTest(campo=campo, payload=payload):
                    antes = Solicitud.objects.count()
                    respuesta = self.client.post(
                        "/", self.datos(**{campo: payload}), secure=True
                    )
                    self.assertEqual(respuesta.status_code, 200)
                    self.assertEqual(Solicitud.objects.count(), antes)

    def test_texto_libre_con_sql_se_guarda_como_dato_inofensivo(self):
        # El motivo es texto libre: se acepta, pero se guarda LITERAL
        # (consulta parametrizada) y no se ejecuta nada.
        payload = "'; DROP TABLE pacientes_solicitud; -- dolor fuerte"
        antes = Solicitud.objects.count()
        respuesta = self.client.post(
            "/", self.datos(motivo_consulta=payload), secure=True
        )
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(Solicitud.objects.count(), antes + 1)
        self.assertEqual(Solicitud.objects.latest("pk").motivo_consulta, payload)
        # La tabla sigue viva y consultable.
        self.assertEqual(Solicitud.objects.filter(motivo_consulta=payload).count(), 1)

    def test_login_con_inyeccion_sql_no_inicia_sesion(self):
        User.objects.create_user("admin", password="clave-segura-123")
        for payload in PAYLOADS_SQL:
            with self.subTest(payload=payload):
                respuesta = self.client.post(
                    reverse("seguridad:login"),
                    {"username": f"admin{payload}", "password": payload},
                    secure=True,
                )
                self.assertEqual(respuesta.status_code, 200)
                self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(User.objects.count(), 1)


class InyeccionParametrosTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.coordinador = User.objects.create_user("coord_inyeccion")
        cls.coordinador.groups.add(Group.objects.get_or_create(name="Coordinador")[0])
        cls.estudiante = User.objects.create_user("est_inyeccion")
        cls.estudiante.groups.add(Group.objects.get_or_create(name="Estudiante")[0])
        cls.especialidad = Especialidad.objects.create(
            nombre="Especialidad de Prueba (inyección GET)"
        )
        cls.solicitud = Solicitud.objects.create(
            nombre_completo="Paciente Inyección",
            rut="66666666-6",
            fecha_nacimiento=date(1990, 1, 1),
            telefono="+56912345678",
            motivo_consulta="Dolor",
            especialidad=cls.especialidad,
        )

    def setUp(self):
        self.client.force_login(self.coordinador)

    def test_filtros_get_con_sql_no_rompen_ni_filtran_datos(self):
        url = reverse("coordinacion:listado_solicitudes")
        total = Solicitud.objects.count()
        for parametro in ("especialidad", "fecha", "estado"):
            for payload in PAYLOADS_SQL:
                with self.subTest(parametro=parametro, payload=payload):
                    respuesta = self.client.get(url, {parametro: payload}, secure=True)
                    self.assertEqual(respuesta.status_code, 200)
                    self.assertEqual(Solicitud.objects.count(), total)
        self.assertEqual(User.objects.filter(username="coord_inyeccion").count(), 1)

    def test_derivar_con_sql_en_el_estudiante_no_deriva(self):
        url = reverse("coordinacion:derivar_solicitud", args=[self.solicitud.pk])
        for payload in PAYLOADS_SQL:
            with self.subTest(payload=payload):
                respuesta = self.client.post(
                    url, {"estudiante_asignado": payload}, secure=True
                )
                self.assertEqual(respuesta.status_code, 302)
                self.solicitud.refresh_from_db()
                self.assertEqual(self.solicitud.estado, Solicitud.Estado.PENDIENTE)
                self.assertIsNone(self.solicitud.estudiante_asignado)

    def test_url_de_detalle_solo_acepta_enteros(self):
        # <int:pk> en la ruta: un payload en la URL ni siquiera llega a la vista.
        self.client.force_login(self.estudiante)
        for payload in ("1 OR 1=1", "1;DROP TABLE x", "abc"):
            with self.subTest(payload=payload):
                respuesta = self.client.get(
                    f"/detalle/{payload}/", secure=True
                )
                self.assertEqual(respuesta.status_code, 404)


class XSSAlmacenadoTests(TestCase):
    SCRIPT = "<script>alert('xss')</script>"

    @classmethod
    def setUpTestData(cls):
        cls.coordinador = User.objects.create_user("coord_xss")
        cls.coordinador.groups.add(Group.objects.get_or_create(name="Coordinador")[0])
        cls.estudiante = User.objects.create_user("est_xss")
        cls.estudiante.groups.add(Group.objects.get_or_create(name="Estudiante")[0])
        especialidad = Especialidad.objects.create(
            nombre="Especialidad de Prueba (XSS)"
        )
        # Se crea por el ORM para saltarse el formulario: simula un dato
        # malicioso ya guardado y comprueba que igual se muestra escapado.
        cls.solicitud = Solicitud.objects.create(
            nombre_completo=cls.SCRIPT,
            rut="77777777-7",
            fecha_nacimiento=date(1990, 1, 1),
            telefono="+56912345678",
            motivo_consulta=cls.SCRIPT,
            experiencia_previa=cls.SCRIPT,
            especialidad=especialidad,
            estudiante_asignado=cls.estudiante,
        )

    def _assert_escapado(self, respuesta):
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotContains(respuesta, self.SCRIPT)
        self.assertContains(respuesta, "&lt;script&gt;")

    def test_listado_del_coordinador_escapa_el_html(self):
        self.client.force_login(self.coordinador)
        self._assert_escapado(
            self.client.get(reverse("coordinacion:listado_solicitudes"), secure=True)
        )

    def test_mis_pacientes_escapa_el_html(self):
        self.client.force_login(self.estudiante)
        self._assert_escapado(
            self.client.get(reverse("estudiantes:mis_pacientes"), secure=True)
        )

    def test_detalle_del_paciente_escapa_el_html(self):
        self.client.force_login(self.estudiante)
        url = reverse("pacientes:detalle_paciente", args=[self.solicitud.pk])
        self._assert_escapado(self.client.get(url, secure=True))


class GuardiaEstaticaTests(TestCase):
    """Si alguien introduce una construcción insegura, el CI se pone rojo."""

    RAIZ = Path(__file__).resolve().parent.parent
    EXCLUIDOS = {"venv", ".venv", ".git", "staticfiles", "node_modules", "migrations", "__pycache__"}

    PATRONES_PY = {
        "SQL crudo (.raw)": r"\.raw\(",
        "SQL crudo (.extra)": r"\.extra\(",
        "SQL crudo (RawSQL)": r"\bRawSQL\b",
        "cursor directo": r"\bcursor\(\)|connection\.cursor",
        "mark_safe": r"\bmark_safe\b",
        "csrf_exempt": r"\bcsrf_exempt\b",
        "eval/exec": r"\b(eval|exec)\(",
        "os.system": r"\bos\.system\(",
    }
    PATRONES_HTML = {
        "filtro |safe": r"\|\s*safe\b",
        "autoescape off": r"\{%\s*autoescape\s+off",
    }

    def _archivos(self, sufijo):
        for ruta in self.RAIZ.rglob(f"*{sufijo}"):
            partes = set(ruta.relative_to(self.RAIZ).parts)
            if partes & self.EXCLUIDOS:
                continue
            if ruta.name.startswith("test") or ruta.name == "tests.py":
                continue
            yield ruta

    def _buscar(self, sufijo, patrones):
        hallazgos = []
        for ruta in self._archivos(sufijo):
            texto = ruta.read_text(encoding="utf-8", errors="ignore")
            for nombre, patron in patrones.items():
                if re.search(patron, texto):
                    hallazgos.append(f"{ruta.relative_to(self.RAIZ)}: {nombre}")
        return hallazgos

    def test_codigo_python_sin_construcciones_inseguras(self):
        self.assertEqual(self._buscar(".py", self.PATRONES_PY), [])

    def test_plantillas_sin_desactivar_el_escape(self):
        self.assertEqual(self._buscar(".html", self.PATRONES_HTML), [])
