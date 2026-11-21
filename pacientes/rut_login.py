# ============================================
# Ingreso del paciente con su RUT (sin guardar el RUT en claro)
# --------------------------------------------
# El RUT de PerfilPaciente va cifrado (REQ-08) y por eso no se puede buscar.
# Para poder encontrar al paciente al iniciar sesión se guarda un "índice
# ciego": HMAC-SHA256 del RUT normalizado, con una clave del servidor. Sin esa
# clave el hash no sirve para adivinar RUTs, y en la base nunca queda el RUT
# legible ni como nombre de usuario.
# ============================================
import re

from django.conf import settings
from django.utils.crypto import salted_hmac

from .validators import limpiar_rut

_PATRON = re.compile(r"^\d{7,8}[0-9K]$")


def hash_rut(valor):
    """Hash estable del RUT (sin puntos ni guion), o None si no parece un RUT."""
    if not valor:
        return None
    limpio = limpiar_rut(str(valor))
    if not _PATRON.match(limpio):
        return None
    return salted_hmac(
        "pacientes.rut_login", limpio, secret=settings.FIELD_ENCRYPTION_KEY,
        algorithm="sha256",
    ).hexdigest()
