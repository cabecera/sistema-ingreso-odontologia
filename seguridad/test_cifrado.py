# ============================================
# Task 57: Confirmar que todos los datos sensibles queden protegidos
# Issue padre: REQ-08 (Cifrado de datos sensibles)
# --------------------------------------------
# Lee las tablas con SQL directo (sin pasar por el ORM, que descifra solo)
# y comprueba que en la base de datos NO queda ningún dato sensible en
# texto plano, mientras que el ORM sí los devuelve descifrados.
#   - Solicitud: RUT y antecedentes de salud.
#   - PerfilPaciente: RUT.
#   - FichaClinica: examen previo, observaciones y reporte.
# Además, un test recorre TODOS los modelos de las apps del proyecto: si
# alguien agrega un campo sensible sin cifrar, falla (ver CAMPOS_PUBLICOS).
# ============================================

from datetime import date

from django.apps import apps
from django.contrib.auth.models import User
from django.db import connection
from django.test import TestCase
from encrypted_model_fields.fields import EncryptedMixin

from administracion.models import Especialidad
from pacientes.models import FichaClinica, PerfilPaciente, Solicitud

RUT = "12345678-5"
ANTECEDENTES_P = "Alergia a la penicilina (dato personal de prueba)"
ANTECEDENTES_F = "Diabetes en la familia (dato familiar de prueba)"
EXAMEN = "Examen: absceso en pieza 36 (dato clínico de prueba)"
OBSERVACIONES = "Observación: paciente ansioso (dato clínico de prueba)"
REPORTE = "Reporte: requiere endodoncia (dato clínico de prueba)"

# Campos de las apps del proyecto que NO son sensibles y por eso pueden ir en
# texto plano. Todo campo de texto que no esté aquí debe estar cifrado.
CAMPOS_PUBLICOS = {
    "administracion.Especialidad": {"nombre", "descripcion"},
    "pacientes.Solicitud": {
        "nombre_completo", "telefono", "motivo_consulta", "experiencia_previa", "estado",
    },
    # rut_hash es un HMAC con clave del servidor (no es el RUT ni permite recuperarlo).
    "pacientes.PerfilPaciente": {"nombre_completo", "telefono", "estado", "rut_hash"},
    "pacientes.FichaClinica": set(),
    "seguridad.BitacoraAuditoria": {"accion", "detalles"},
}


def fila_cruda(tabla, columnas):
    """Devuelve la primera fila tal como está guardada en la base de datos."""
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT {', '.join(columnas)} FROM {tabla}")  # nosec B608 - nombres fijos del test
        return cursor.fetchone()


class DatosSensiblesCifradosTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.especialidad = Especialidad.objects.create(nombre="Esp (tests cifrado)", activa=True)
        cls.usuario = User.objects.create_user("cifrado_est", password="Clave-Segura#2026x")
        cls.solicitud = Solicitud.objects.create(
            nombre_completo="María José Pérez", fecha_nacimiento=date(1990, 1, 1), rut=RUT,
            telefono="+56 9 1234 5678", motivo_consulta="Dolor de muelas hace una semana",
            especialidad=cls.especialidad, estado="REALIZADO", estudiante_asignado=cls.usuario,
            antecedentes_personales=ANTECEDENTES_P, antecedentes_familiares=ANTECEDENTES_F,
        )
        cls.perfil = PerfilPaciente.objects.create(
            usuario=cls.usuario, nombre_completo="María José Pérez",
            fecha_nacimiento=date(1990, 1, 1), rut=RUT, telefono="+56 9 1234 5678",
        )
        cls.ficha = FichaClinica.objects.create(
            solicitud=cls.solicitud, estudiante=cls.usuario, examen_previo=EXAMEN,
            observaciones=OBSERVACIONES, especialidad_requerida=cls.especialidad, reporte=REPORTE,
        )

    def comprobar_cifrado(self, tabla, columnas, secretos):
        crudo = fila_cruda(tabla, columnas)
        for valor in crudo:
            self.assertTrue(valor, f"{tabla}: columna vacía")
            for secreto in secretos:
                self.assertNotIn(secreto, valor, f"{tabla}: dato sensible en texto plano")
            # Fernet siempre produce un token que empieza con "gAAAA".
            self.assertTrue(valor.startswith("gAAAA"), f"{tabla}: valor sin cifrar")

    def test_solicitud_rut_y_antecedentes_cifrados_en_la_base(self):
        self.comprobar_cifrado(
            "pacientes_solicitud",
            ["rut", "antecedentes_personales", "antecedentes_familiares"],
            ["12345678", "penicilina", "Diabetes"],
        )

    def test_perfil_paciente_rut_cifrado_en_la_base(self):
        self.comprobar_cifrado("pacientes_perfilpaciente", ["rut"], ["12345678"])

    def test_ficha_clinica_cifrada_en_la_base(self):
        self.comprobar_cifrado(
            "pacientes_fichaclinica",
            ["examen_previo", "observaciones", "reporte"],
            ["absceso", "ansioso", "endodoncia"],
        )

    def test_el_orm_devuelve_los_datos_descifrados(self):
        s = Solicitud.objects.get(pk=self.solicitud.pk)
        self.assertEqual(s.rut, RUT)
        self.assertEqual(s.antecedentes_personales, ANTECEDENTES_P)
        self.assertEqual(s.antecedentes_familiares, ANTECEDENTES_F)
        self.assertEqual(PerfilPaciente.objects.get(pk=self.perfil.pk).rut, RUT)
        f = FichaClinica.objects.get(pk=self.ficha.pk)
        self.assertEqual((f.examen_previo, f.observaciones, f.reporte), (EXAMEN, OBSERVACIONES, REPORTE))

    def test_los_datos_sensibles_no_aparecen_en_las_tablas_sin_cifrar(self):
        # Bitácora y usuario no deben contener RUT ni contenido clínico.
        with connection.cursor() as cursor:
            for tabla in ("seguridad_bitacoraauditoria", "auth_user"):
                cursor.execute(f"SELECT * FROM {tabla}")  # nosec B608 - nombres fijos del test
                for fila in cursor.fetchall():
                    texto = " ".join(str(c) for c in fila)
                    for secreto in ("12345678", "penicilina", "absceso", "endodoncia"):
                        self.assertNotIn(secreto, texto, tabla)

    def test_todo_campo_de_texto_de_los_modelos_es_publico_o_esta_cifrado(self):
        # Guardia: si alguien agrega un CharField/TextField nuevo sin cifrar y
        # sin declararlo público en CAMPOS_PUBLICOS, este test falla.
        revisados = 0
        for etiqueta, publicos in CAMPOS_PUBLICOS.items():
            modelo = apps.get_model(etiqueta)
            for campo in modelo._meta.get_fields():
                if not getattr(campo, "concrete", False) or campo.is_relation or campo.primary_key:
                    continue
                if campo.get_internal_type() not in ("CharField", "TextField"):
                    continue
                revisados += 1
                if campo.name in publicos:
                    self.assertNotIsInstance(campo, EncryptedMixin)
                else:
                    self.assertIsInstance(
                        campo, EncryptedMixin,
                        f"{etiqueta}.{campo.name} es de texto, no está cifrado y no está declarado público",
                    )
        self.assertGreater(revisados, 15)

    def test_la_guardia_cubre_todos_los_modelos_del_proyecto(self):
        propios = {
            f"{m._meta.app_label}.{m.__name__}"
            for app in ("administracion", "pacientes", "seguridad", "coordinacion", "estudiantes")
            for m in apps.get_app_config(app).get_models()
        }
        self.assertEqual(propios - set(CAMPOS_PUBLICOS), set(),
                         "Hay modelos nuevos sin revisar en CAMPOS_PUBLICOS")
