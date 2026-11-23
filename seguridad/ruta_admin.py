# ============================================
# Ruta del sitio /admin/ de Django (OWASP A05: configuración de seguridad)
# --------------------------------------------
# La ruta estándar /admin/ es la primera que prueba cualquier escáner. Con la
# variable de entorno ADMIN_URL se puede cambiar por otra que no se adivine
# (por ejemplo, ADMIN_URL=gestion-k8x2q9). Si no se define, se mantiene "admin/".
# La ruta nueva no reemplaza al login: el admin sigue protegido por usuario,
# contraseña y rol. Solo deja de ser un destino evidente.
# ============================================
import re

from django.core.exceptions import ImproperlyConfigured

RUTA_POR_DEFECTO = "admin"
_PERMITIDO = re.compile(r"^[A-Za-z0-9_\-]+(/[A-Za-z0-9_\-]+)*$")


def normalizar_ruta_admin(valor):
    """Devuelve la ruta lista para usar en urls.py: sin barra inicial y con barra final."""
    limpio = (valor or "").strip().strip("/") or RUTA_POR_DEFECTO
    if not _PERMITIDO.match(limpio):
        raise ImproperlyConfigured(
            "ADMIN_URL solo puede tener letras, números, guiones y barras (por ejemplo: gestion-k8x2q9)."
        )
    return limpio + "/"
