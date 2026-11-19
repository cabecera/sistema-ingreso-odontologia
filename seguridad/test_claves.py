# Task 58: la clave de cifrado no se guarda en el repo ni se acepta una de prueba en producción.
import re
from pathlib import Path

from cryptography.fernet import Fernet
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from seguridad.claves import (
    CLAVE_CIFRADO_DE_PRUEBA,
    CLAVE_SECRETA_DE_PRUEBA,
    es_produccion,
    validar_claves,
)

RAIZ = Path(__file__).resolve().parent.parent
CLAVE_REAL = Fernet.generate_key().decode()
SECRETA_REAL = "una-clave-secreta-larga-y-aleatoria-para-la-prueba-1234567890"


def validar(**cambios):
    datos = dict(
        debug=False,
        usa_sqlite=False,
        secret_key=SECRETA_REAL,
        clave_cifrado=CLAVE_REAL,
    )
    datos.update(cambios)
    return validar_claves(**datos)


class ValidacionDeClavesTests(SimpleTestCase):
    def test_produccion_es_debug_apagado_y_base_real(self):
        self.assertTrue(es_produccion(debug=False, usa_sqlite=False))
        self.assertFalse(es_produccion(debug=True, usa_sqlite=False))
        self.assertFalse(es_produccion(debug=False, usa_sqlite=True))

    def test_produccion_con_claves_reales_arranca(self):
        validar()  # no lanza

    def test_produccion_rechaza_la_clave_de_cifrado_de_prueba(self):
        for clave in (CLAVE_CIFRADO_DE_PRUEBA, "", None):
            with self.subTest(clave=clave):
                with self.assertRaises(ImproperlyConfigured):
                    validar(clave_cifrado=clave)

    def test_produccion_rechaza_la_secret_key_de_prueba(self):
        for clave in (CLAVE_SECRETA_DE_PRUEBA, "", None):
            with self.subTest(clave=clave):
                with self.assertRaises(ImproperlyConfigured):
                    validar(secret_key=clave)

    def test_produccion_rechaza_una_clave_fernet_invalida(self):
        for clave in ("genera_tu_propia_llave_con_el_comando_de_arriba", "corta", "x" * 44):
            with self.subTest(clave=clave):
                with self.assertRaises(ImproperlyConfigured):
                    validar(clave_cifrado=clave)

    def test_ci_y_desarrollo_aceptan_las_claves_de_prueba(self):
        # DEBUG encendido o SQLite (el CI): no se exige nada.
        validar(debug=True, clave_cifrado=CLAVE_CIFRADO_DE_PRUEBA, secret_key=CLAVE_SECRETA_DE_PRUEBA)
        validar(usa_sqlite=True, clave_cifrado=CLAVE_CIFRADO_DE_PRUEBA, secret_key=CLAVE_SECRETA_DE_PRUEBA)

    def test_el_mensaje_de_error_no_revela_las_claves(self):
        with self.assertRaises(ImproperlyConfigured) as contexto:
            validar(clave_cifrado=CLAVE_CIFRADO_DE_PRUEBA)
        self.assertNotIn(CLAVE_CIFRADO_DE_PRUEBA, str(contexto.exception))


class ClaveEnElProyectoTests(SimpleTestCase):
    def test_la_clave_configurada_es_una_clave_fernet_valida(self):
        Fernet(settings.FIELD_ENCRYPTION_KEY)  # no lanza

    def test_env_esta_ignorado_por_git(self):
        lineas = (RAIZ / ".gitignore").read_text().splitlines()
        self.assertIn(".env", [l.strip() for l in lineas])

    def test_ningun_archivo_del_proyecto_contiene_una_clave_real(self):
        # Solo la clave de prueba pública puede aparecer en el repo.
        excluidos = {"venv", ".venv", ".git", "staticfiles", "node_modules", "__pycache__"}
        extensiones = {".py", ".yml", ".yaml", ".example", ".md", ".txt", ".sh"}
        patron = re.compile(r"FIELD_ENCRYPTION_KEY\s*=\s*['\"]?([A-Za-z0-9_\-]{43}=)['\"]?")
        hallazgos = []
        for ruta in RAIZ.rglob("*"):
            relativa = ruta.relative_to(RAIZ)
            if not ruta.is_file() or set(relativa.parts) & excluidos:
                continue
            if ruta.suffix not in extensiones:
                continue
            texto = ruta.read_text(encoding="utf-8", errors="ignore")
            for clave in patron.findall(texto):
                if clave != CLAVE_CIFRADO_DE_PRUEBA:
                    hallazgos.append(f"{relativa}: {clave[:6]}…")
        self.assertEqual(hallazgos, [])
