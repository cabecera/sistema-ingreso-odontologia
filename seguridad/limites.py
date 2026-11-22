# ============================================
# Límites de uso por dirección IP (OWASP A06 diseño inseguro / A07 autenticación)
# --------------------------------------------
# El plan gratuito de Render tiene poca capacidad: si alguien dispara muchas
# peticiones, el servidor responde 429 (Too Many Requests) en vez de saturarse.
# - General: tope de peticiones por minuto por IP (los archivos estáticos no cuentan).
# - Envíos (POST): tope más estricto por minuto.
# - Registro público: tope por hora (evita llenar la lista del coordinador de basura).
# - Login: tope por minuto por IP; además el bloqueo por intentos fallidos se lleva
#   por IP + identificador, para que un atacante no pueda bloquear la cuenta de otra
#   persona desde su propia conexión.
# Los contadores viven en el caché del servidor (sin datos personales: solo IP
# y números). Cada worker de gunicorn tiene el suyo, por eso los topes son generosos.
# ============================================
import hashlib

from django.conf import settings
from django.core.cache import cache, caches
from django.http import HttpResponse

PAGINA_429 = (
    "<!doctype html><html lang='es'><head><meta charset='utf-8'>"
    "<meta name='viewport' content='width=device-width, initial-scale=1'>"
    "<title>Demasiadas peticiones</title></head><body>"
    "<h1>Demasiadas peticiones</h1>"
    "<p>Hiciste muchas solicitudes en poco tiempo. Espera un momento e inténtalo de nuevo.</p>"
    "</body></html>"
)


def ip_cliente(request):
    """IP del cliente detrás del proxy de Render.

    X-Forwarded-For lo arma el proxy agregando cada salto al final; lo que
    escribe el cliente queda al principio y es falsificable. Por eso se toma la
    entrada contando desde el final según LIMITES_SALTOS_PROXY."""
    cadena = [p.strip() for p in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",") if p.strip()]
    saltos = max(1, int(getattr(settings, "LIMITES_SALTOS_PROXY", 1)))
    if cadena:
        return cadena[-saltos] if len(cadena) >= saltos else cadena[0]
    return request.META.get("REMOTE_ADDR", "desconocida")


def _clave(*partes):
    texto = ":".join(str(p) for p in partes)
    return "lim:" + hashlib.sha256(texto.encode()).hexdigest()[:32]


def bloqueos():
    """Almacén de los intentos fallidos de login.

    Gunicorn corre con varios procesos y cada uno tiene su propia memoria: un
    contador en memoria se repartiría entre ellos y el bloqueo tardaría el doble
    en llegar. Estos contadores viven en la base de datos (tabla de caché), así
    que todos los procesos ven el mismo número y además sobreviven a un reinicio."""
    return caches["bloqueos"]


def contar(clave, ventana, almacen=None):
    """Suma 1 al contador de la ventana y devuelve el total."""
    almacen = almacen or cache
    almacen.add(clave, 0, ventana)
    try:
        return almacen.incr(clave)
    except ValueError:  # venció justo ahora
        almacen.set(clave, 1, ventana)
        return 1


def superado(clave, tope, almacen=None):
    return (almacen or cache).get(clave, 0) >= tope


class LimiteDePeticionesMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def _limites(self, request):
        ruta = request.path
        reglas = [("general", settings.LIMITE_GENERAL_POR_MINUTO, 60)]
        if request.method == "POST":
            reglas.append(("post", settings.LIMITE_POST_POR_MINUTO, 60))
            if ruta.startswith("/login"):
                reglas.append(("login", settings.LIMITE_LOGIN_POR_MINUTO, 60))
            if ruta.startswith("/registro"):
                reglas.append(("registro", settings.LIMITE_REGISTRO_POR_HORA, 3600))
        return reglas

    def __call__(self, request):
        if (
            not getattr(settings, "LIMITES_ACTIVOS", True)
            or request.path.startswith(settings.STATIC_URL)
        ):
            return self.get_response(request)
        ip = ip_cliente(request)
        for nombre, tope, ventana in self._limites(request):
            if contar(_clave(nombre, ip), ventana) > tope:
                respuesta = HttpResponse(PAGINA_429, status=429, content_type="text/html; charset=utf-8")
                respuesta["Retry-After"] = str(ventana if ventana <= 60 else 600)
                return respuesta
        return self.get_response(request)
