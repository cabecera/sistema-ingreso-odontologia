# ============================================
# Task 55: Reforzar las validaciones de todos los formularios
# --------------------------------------------
# Pruebas de las validaciones del formulario público de solicitud
# y de los filtros por GET del listado del coordinador. Cada caso
# "inválido" comprueba que el servidor rechaza el dato aunque el
# navegador no lo haya detenido.
# ============================================

from django.contrib.auth.models import Group, User
from django.test import TestCase

from administracion.models import Especialidad

from .forms import LIMITES_TEXTO, SolicitudForm
from .models import Solicitud


class SolicitudFormValidacionTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        # Nombre distinto al catálogo real (único y sembrado por migración).
        cls.especialidad = Especialidad.objects.create(
            nombre="Especialidad de Prueba (tests formulario)", activa=True
        )

    def datos(self, **cambios):
        base = {
            "nombre_completo": "María José Pérez",
            "fecha_nacimiento": "1990-01-01",
            "rut": "12.345.678-5",
            "telefono": "+56 9 1234 5678",
            "especialidad": self.especialidad.pk,
            "motivo_consulta": "Dolor de muelas hace una semana",
            "experiencia_previa": "",
            "antecedentes_personales": "",
            "antecedentes_familiares": "",
        }
        base.update(cambios)
        return base

    def test_datos_validos_son_aceptados(self):
        form = SolicitudForm(self.datos())
        self.assertTrue(form.is_valid(), form.errors)

    # --- nombre_completo ---
    def test_nombre_con_tildes_enie_apostrofe_y_guion_es_valido(self):
        form = SolicitudForm(self.datos(nombre_completo="María José O'Higgins-Núñez"))
        self.assertTrue(form.is_valid(), form.errors)

    def test_nombre_con_numeros_es_rechazado(self):
        form = SolicitudForm(self.datos(nombre_completo="Juan Perez 123"))
        self.assertIn("nombre_completo", form.errors)

    def test_nombre_con_etiquetas_html_es_rechazado(self):
        form = SolicitudForm(self.datos(nombre_completo="<script>alert(1)</script>"))
        self.assertIn("nombre_completo", form.errors)

    def test_nombre_demasiado_corto_es_rechazado(self):
        form = SolicitudForm(self.datos(nombre_completo="Ab"))
        self.assertIn("nombre_completo", form.errors)

    def test_nombre_solo_signos_es_rechazado(self):
        form = SolicitudForm(self.datos(nombre_completo="- - - -"))
        self.assertIn("nombre_completo", form.errors)

    def test_nombre_normaliza_espacios_repetidos(self):
        form = SolicitudForm(self.datos(nombre_completo="  Juan     Pérez  "))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["nombre_completo"], "Juan Pérez")

    # --- motivo_consulta ---
    def test_motivo_demasiado_corto_es_rechazado(self):
        form = SolicitudForm(self.datos(motivo_consulta="dolor"))
        self.assertIn("motivo_consulta", form.errors)

    def test_motivo_solo_espacios_es_rechazado(self):
        form = SolicitudForm(self.datos(motivo_consulta="            "))
        self.assertIn("motivo_consulta", form.errors)

    def test_motivo_sobre_el_limite_es_rechazado(self):
        largo = "a" * (LIMITES_TEXTO["motivo_consulta"] + 1)
        form = SolicitudForm(self.datos(motivo_consulta=largo))
        self.assertIn("motivo_consulta", form.errors)

    # --- caracteres de control ---
    def test_caracteres_de_control_se_eliminan_de_los_textos(self):
        form = SolicitudForm(self.datos(
            motivo_consulta="Dolor de muelas\x07 muy fuerte",
            antecedentes_personales="Alergia\x1b a la penicilina",
        ))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["motivo_consulta"], "Dolor de muelas muy fuerte")
        self.assertEqual(form.cleaned_data["antecedentes_personales"], "Alergia a la penicilina")

    def test_caracter_nulo_es_rechazado(self):
        form = SolicitudForm(self.datos(motivo_consulta="Dolor\x00 de muelas fuerte"))
        self.assertIn("motivo_consulta", form.errors)

    # --- otros campos ya validados: se fijan para que no se rompan ---
    def test_rut_invalido_es_rechazado(self):
        form = SolicitudForm(self.datos(rut="12345678-9"))
        self.assertIn("rut", form.errors)

    def test_telefono_con_letras_es_rechazado(self):
        form = SolicitudForm(self.datos(telefono="abc12345678"))
        self.assertIn("telefono", form.errors)

    def test_fecha_futura_es_rechazada(self):
        form = SolicitudForm(self.datos(fecha_nacimiento="2999-01-01"))
        self.assertIn("fecha_nacimiento", form.errors)

    def test_especialidad_inexistente_es_rechazada(self):
        form = SolicitudForm(self.datos(especialidad=999999))
        self.assertIn("especialidad", form.errors)


class SolicitudVistaPublicaTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.especialidad = Especialidad.objects.create(
            nombre="Especialidad de Prueba (tests vista publica)", activa=True
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

    def test_post_valido_crea_la_solicitud(self):
        antes = Solicitud.objects.count()
        response = self.client.post("/", self.datos(), secure=True)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Solicitud.objects.count(), antes + 1)

    def test_post_con_nombre_invalido_no_crea_nada(self):
        antes = Solicitud.objects.count()
        response = self.client.post(
            "/", self.datos(nombre_completo="<b>Ana</b> 123"), secure=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Solicitud.objects.count(), antes)


class FiltrosListadoCoordinadorTests(TestCase):
    """Los parámetros GET vienen del usuario: valores raros no deben
    romper la página (500) ni reflejarse tal cual en el HTML."""

    URL = "/coordinacion/listado/"

    @classmethod
    def setUpTestData(cls):
        grupo, _ = Group.objects.get_or_create(name="Coordinador")
        cls.coordinador = User.objects.create_user(
            username="coord_validaciones", password="password123"
        )
        cls.coordinador.groups.add(grupo)

    def setUp(self):
        self.client.login(username="coord_validaciones", password="password123")

    def test_fecha_con_texto_se_ignora(self):
        response = self.client.get(self.URL, {"fecha": "no-es-fecha"}, secure=True)
        self.assertEqual(response.status_code, 200)

    def test_fecha_en_el_limite_maximo_no_rompe(self):
        response = self.client.get(self.URL, {"fecha": "9999-12-31"}, secure=True)
        self.assertEqual(response.status_code, 200)

    def test_especialidad_con_intento_de_inyeccion_se_ignora(self):
        response = self.client.get(
            self.URL, {"especialidad": "1 OR 1=1"}, secure=True
        )
        self.assertEqual(response.status_code, 200)

    def test_estado_con_html_no_se_refleja_en_la_pagina(self):
        response = self.client.get(
            self.URL, {"estado": "<script>alert(1)</script>"}, secure=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "<script>alert(1)</script>")
