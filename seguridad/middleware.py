# ============================================
# Cabeceras de seguridad (OWASP A02: configuración de seguridad)
# --------------------------------------------
# - Content-Security-Policy: solo se ejecuta lo que sale del propio sitio y de
#   los dos CDN que usa la página (Bootstrap y Google Fonts). Sin scripts en
#   línea; el único <style> en línea lleva un "nonce" distinto en cada respuesta.
# - Permissions-Policy: la aplicación no necesita cámara, micrófono, ubicación, etc.
# - Bloquea los métodos TRACE y TRACK (405): sirven para robar cookies en
#   ataques antiguos y no los usa nadie.
# El sitio /admin/ de Django usa scripts y estilos en línea propios, por eso
# lleva una política algo más amplia (solo para el Super Administrador).
# ============================================
import secrets

from django.http import HttpResponseNotAllowed

METODOS_BLOQUEADOS = {"TRACE", "TRACK"}
PERMISSIONS_POLICY = (
    "accelerometer=(), camera=(), geolocation=(), gyroscope=(), "
    "magnetometer=(), microphone=(), payment=(), usb=()"
)


def politica_csp(nonce, es_admin=False):
    estilos = "'self' https://cdn.jsdelivr.net https://fonts.googleapis.com"
    scripts = "'self' https://cdn.jsdelivr.net"
    if es_admin:
        estilos += " 'unsafe-inline'"
        scripts += " 'unsafe-inline'"
    else:
        estilos += f" 'nonce-{nonce}'"
    return "; ".join([
        "default-src 'self'",
        f"script-src {scripts}",
        f"style-src {estilos}",
        "font-src 'self' https://fonts.gstatic.com",
        "img-src 'self' data:",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ])


class CabecerasSeguridadMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method in METODOS_BLOQUEADOS:
            return HttpResponseNotAllowed(["GET", "HEAD", "POST", "OPTIONS"])
        request.csp_nonce = secrets.token_urlsafe(16)
        response = self.get_response(request)
        response["Content-Security-Policy"] = politica_csp(
            request.csp_nonce, es_admin=request.path.startswith("/admin/")
        )
        response.setdefault("Permissions-Policy", PERMISSIONS_POLICY)
        return response
