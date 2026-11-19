# ============================================
# Task 58: Guardar la clave de cifrado de forma segura (REQ-08)
# --------------------------------------------
# Las claves reales viven SOLO en variables de entorno (.env local,
# Variables de Render en producción) y nunca en el repositorio.
# Para que el CI y los tests no necesiten secretos reales, settings.py
# usa valores de prueba por defecto; como esos valores son públicos
# (están en el repo), en producción NO se aceptan: si falta la
# variable, la app se niega a arrancar ("fallar fuerte antes que
# cifrar con una clave conocida por cualquiera").
#
# Producción = DEBUG apagado y base de datos real (no SQLite). El CI
# corre con SQLite y genera su propia clave aleatoria en cada corrida.
#
# Este módulo no importa modelos para poder usarse desde settings.py.
# ============================================

from cryptography.fernet import Fernet
from django.core.exceptions import ImproperlyConfigured

# Valores públicos, solo para CI y pruebas locales.
CLAVE_SECRETA_DE_PRUEBA = "django-insecure-ci-only-key-para-pruebas"
CLAVE_CIFRADO_DE_PRUEBA = "Xq7v9B2wR1sE4dF5gH6jK7lM8nO9pQ0rS1tU2vW3xY4="


def es_produccion(debug, usa_sqlite):
    return not debug and not usa_sqlite


def validar_claves(debug, usa_sqlite, secret_key, clave_cifrado):
    """Lanza ImproperlyConfigured si producción usa claves de prueba o inválidas."""
    if not es_produccion(debug, usa_sqlite):
        return

    if not secret_key or secret_key == CLAVE_SECRETA_DE_PRUEBA:
        raise ImproperlyConfigured(
            "Falta la variable de entorno SECRET_KEY (o es la clave de prueba "
            "pública). Defínela en el entorno de producción."
        )

    if not clave_cifrado or clave_cifrado == CLAVE_CIFRADO_DE_PRUEBA:
        raise ImproperlyConfigured(
            "Falta la variable de entorno FIELD_ENCRYPTION_KEY (o es la clave de "
            "prueba pública). Genérala con Fernet.generate_key() y defínela en "
            "el entorno de producción."
        )

    try:
        Fernet(clave_cifrado)
    except (ValueError, TypeError) as error:
        raise ImproperlyConfigured(
            "FIELD_ENCRYPTION_KEY no es una clave Fernet válida "
            "(32 bytes en base64 url-safe)."
        ) from error
