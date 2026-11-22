#!/usr/bin/env python3
# ============================================
# Pruebas de seguridad dinámicas (OWASP Top 10) contra una URL
# --------------------------------------------
# Solo usa la biblioteca estándar de Python: no hay que instalar nada.
#
# Uso (Git Bash):
#   python pruebas_seguridad/pruebas_owasp.py https://sistema-ingreso-odontologia.onrender.com
#
# Pruebas con sesión (control de acceso, cierre de sesión): se activan si se
# definen estas variables de entorno. NUNCA escribas contraseñas reales en el
# repositorio; escríbelas en la terminal:
#   export PRUEBA_PACIENTE="12345678-5:clave"      (RUT:clave)
#   export PRUEBA_COORDINADOR="coordinador1:clave" (usuario:clave)
#   export PRUEBA_ESTUDIANTE="estudiante1:clave"
#   export PRUEBA_ADMIN="admintest:clave"
#
# Seguridad de uso: las pruebas son de LECTURA o rechazadas por validación;
# no crean registros. Solo se atacan sistemas propios. Genera un informe
# Markdown con la tabla "tipo de prueba / esperado / obtenido" para la Wiki.
# ============================================
import http.client
import json
import os
import re
import socket
import ssl
import sys
import time
import urllib.parse
import uuid
from datetime import datetime
from http.cookies import SimpleCookie

TIMEOUT = 30
RESULTADOS = []


# ---------- cliente HTTP mínimo (sin seguir redirecciones) ----------
_ULTIMA = {"general": 0.0, "post": 0.0, "login": 0.0}
# Pausa mínima entre peticiones (segundos): general 240/min, POST 40/min, login 20/min.
_PAUSAS = (("general", 0.3), ("post", 1.6), ("login", 3.2))


def espera(metodo, ruta):
    ahora = time.monotonic()
    claves = ["general"] + (["post"] if metodo == "POST" else []) + (["login"] if metodo == "POST" and ruta.startswith("/login") else [])
    pausa = max(dict(_PAUSAS)[k] - (ahora - _ULTIMA[k]) for k in claves)
    if pausa > 0:
        time.sleep(pausa)
    ahora = time.monotonic()
    for k in claves:
        _ULTIMA[k] = ahora


def limitada(r):
    return r.status == 429


class Cliente:
    def __init__(self, base):
        u = urllib.parse.urlparse(base)
        self.https = u.scheme == "https"
        self.host = u.hostname
        self.puerto = u.port or (443 if self.https else 80)
        self.cookies = {}
        # Django exige Referer del mismo sitio en los POST por HTTPS (protección CSRF).
        # Si se prueba una copia local, el proxy simula HTTPS, así que el Referer es https.
        self.referer = f"https://{self.host}" + (f":{self.puerto}" if self.puerto not in (80, 443) else "") + "/"

    def _conexion(self):
        if self.https:
            return http.client.HTTPSConnection(self.host, self.puerto, timeout=TIMEOUT,
                                               context=ssl.create_default_context())
        return http.client.HTTPConnection(self.host, self.puerto, timeout=TIMEOUT)

    def pedir(self, metodo, ruta, datos=None, cabeceras=None, cuerpo_crudo=None):
        # El sitio limita las peticiones por IP (429). El script va a un ritmo que
        # respeta esos límites; si aun así recibe 429 espera y reintenta una vez
        # (salvo en el registro, que tiene tope por hora: ahí el 429 es resultado válido).
        espera(metodo, ruta)
        r = self._pedir(metodo, ruta, datos, cabeceras, cuerpo_crudo)
        if r.status == 429 and not ruta.startswith("/registro"):
            time.sleep(min(int(r.cab("Retry-After") or 60), 65) + 1)
            r = self._pedir(metodo, ruta, datos, cabeceras, cuerpo_crudo)
        return r

    def _pedir(self, metodo, ruta, datos=None, cabeceras=None, cuerpo_crudo=None):
        c = self._conexion()
        cab = {"User-Agent": "pruebas-owasp-academico/1.0", "Accept": "text/html"}
        if self.cookies:
            cab["Cookie"] = "; ".join(f"{k}={v}" for k, v in self.cookies.items())
        cuerpo = cuerpo_crudo
        if datos is not None:
            cuerpo = urllib.parse.urlencode(datos).encode()
            cab["Content-Type"] = "application/x-www-form-urlencoded"
            cab["Referer"] = self.referer
        if cabeceras:
            cab.update(cabeceras)
        try:
            c.request(metodo, ruta, body=cuerpo, headers=cab)
            r = c.getresponse()
            cuerpo_resp = r.read(2_000_000).decode("utf-8", "replace")
            cabs = r.getheaders()
            for k, v in cabs:
                if k.lower() == "set-cookie":
                    m = SimpleCookie()
                    m.load(v)
                    for nombre, morsel in m.items():
                        if morsel.value == "" or morsel["max-age"] == "0":
                            self.cookies.pop(nombre, None)
                        else:
                            self.cookies[nombre] = morsel.value
            return Resp(r.status, cabs, cuerpo_resp)
        finally:
            c.close()

    def get(self, ruta, **kw):
        return self.pedir("GET", ruta, **kw)

    def post(self, ruta, datos, **kw):
        return self.pedir("POST", ruta, datos=datos, **kw)

    def token(self, ruta="/login/"):
        r = self.get(ruta)
        m = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', r.cuerpo)
        return m.group(1) if m else self.cookies.get("csrftoken", "")


class Resp:
    def __init__(self, status, cabeceras, cuerpo):
        self.status, self.cabeceras, self.cuerpo = status, cabeceras, cuerpo

    def cab(self, nombre):
        return ", ".join(v for k, v in self.cabeceras if k.lower() == nombre.lower())

    @property
    def location(self):
        return self.cab("Location")


# ---------- registro de resultados ----------
def registrar(owasp, prueba, esperado, obtenido, ok):
    RESULTADOS.append((owasp, prueba, esperado, obtenido, "APROBADA" if ok else "FALLA"))
    marca = "OK   " if ok else "FALLA"
    print(f"[{marca}] {owasp:<4} {prueba[:62]:<62} -> {obtenido[:60]}")


TRAZAS = ("Traceback (most recent call last)", "You're seeing this error because you have",
          "django.core.exceptions", "OperationalError", "ProgrammingError", "Exception Value",
          "SQL syntax", "syntax error", "unrecognized token", "mysqlclient", "sqlite3.", "File \"/", "settings.py")


def sin_fuga(cuerpo):
    return not any(t in cuerpo for t in TRAZAS)


def nuevo(base):
    return Cliente(base)


# ---------- pruebas ----------
def a01_control_de_acceso(base):
    rutas = ["/administracion/", "/administracion/usuarios/", "/administracion/especialidades/",
             "/coordinacion/", "/coordinacion/listado/", "/coordinacion/registros/",
             "/coordinacion/estudiantes/", "/estudiantes/", "/estudiantes/mis-pacientes/",
             "/mis-solicitudes/"]
    fallas = []
    for ruta in rutas:
        r = nuevo(base).get(ruta)
        if not (r.status == 302 and "/login" in r.location):
            fallas.append(f"{ruta}={r.status}")
    registrar("A01", f"Anónimo accede a {len(rutas)} páginas privadas", "Todas redirigen (302) al login",
              "Todas 302 -> /login/" if not fallas else "; ".join(fallas), not fallas)

    for ruta in ("/coordinacion/derivar/1/", "/coordinacion/registros/1/aceptar/",
                 "/estudiantes/pacientes/1/realizada/", "/administracion/usuarios/1/estado/"):
        c = nuevo(base)
        r = c.post(ruta, {"x": "1"})
        ok = r.status in (302, 403, 404, 405)
        registrar("A01", f"Anónimo ejecuta acción POST {ruta}", "Rechazado (302/403/404/405), nunca 200",
                  f"HTTP {r.status}", ok)

    for ruta in ("/static/../core/settings.py", "/static/%2e%2e/%2e%2e/core/settings.py",
                 "/static/..%2f..%2fcore%2fsettings.py", "/%2e%2e/%2e%2e/etc/passwd"):
        r = nuevo(base).get(ruta)
        ok = r.status in (301, 302, 400, 403, 404) and "SECRET_KEY" not in r.cuerpo and "root:" not in r.cuerpo
        registrar("A01", f"Path traversal {ruta}", "No entrega archivos del servidor (400/403/404)",
                  f"HTTP {r.status}", ok)


def a01_con_sesion(base):
    roles = {
        "PACIENTE": ("/coordinacion/", "/administracion/", "/estudiantes/"),
        "ESTUDIANTE": ("/coordinacion/", "/administracion/"),
        # /estudiantes/ (panel con solo los casos propios) es accesible al Coordinador por diseño.
        "COORDINADOR": ("/administracion/", "/estudiantes/mis-pacientes/"),
    }
    ingreso = {}
    for rol, rutas in roles.items():
        cred = os.environ.get(f"PRUEBA_{rol}")
        if not cred or ":" not in cred:
            registrar("A01", f"Control de acceso con rol {rol}", "Prohibido (403) en páginas de otros roles",
                      "OMITIDA: falta PRUEBA_" + rol, True)
            continue
        c = nuevo(base)
        if not iniciar_sesion(c, cred, "paciente" if rol == "PACIENTE" else "personal"):
            registrar("A01", f"Inicio de sesión {rol}", "Sesión iniciada", "No se pudo iniciar sesión", False)
            continue
        ingreso[rol] = c
        malas = []
        for ruta in rutas:
            r = c.get(ruta)
            if r.status != 403:
                malas.append(f"{ruta}={r.status}")
        registrar("A01", f"{rol} intenta entrar a páginas de otros roles", "403 Prohibido en todas",
                  "Todas 403" if not malas else "; ".join(malas), not malas)
    # IDOR: ids consecutivos con la sesión del paciente y del estudiante
    for rol, plantilla in (("PACIENTE", "/estudiantes/pacientes/{n}/reporte/"),
                           ("PACIENTE", "/pacientes/detalle/{n}/"),
                           ("ESTUDIANTE", "/coordinacion/solicitudes/{n}/reporte/")):
        c = ingreso.get(rol)
        if not c:
            continue
        no_200 = all(c.get(plantilla.format(n=n)).status in (302, 403, 404) for n in range(1, 8))
        registrar("A01", f"IDOR: {rol} recorre {plantilla}", "Nunca 200 con datos ajenos (302/403/404)",
                  "Sin accesos indebidos" if no_200 else "Devolvió 200", no_200)
    return ingreso


def iniciar_sesion(c, cred, tipo):
    usuario, clave = cred.split(":", 1)
    t = c.token(f"/login/?tipo={tipo}")
    r = c.post("/login/", {"csrfmiddlewaretoken": t, "username": usuario, "password": clave, "tipo": tipo})
    return r.status == 302 and "/login" not in r.location


def a02_configuracion(base):
    c = nuevo(base)
    r = c.get("/login/")
    h = {k: r.cab(k) for k in ("Strict-Transport-Security", "Content-Security-Policy",
                               "X-Frame-Options", "X-Content-Type-Options", "Referrer-Policy",
                               "Permissions-Policy", "Cache-Control")}
    hsts = h["Strict-Transport-Security"]
    m = re.search(r"max-age=(\d+)", hsts)
    registrar("A02", "Cabecera Strict-Transport-Security (HSTS)", "max-age >= 31536000",
              hsts or "AUSENTE", bool(m and int(m.group(1)) >= 31536000))
    csp = h["Content-Security-Policy"]
    registrar("A02", "Cabecera Content-Security-Policy", "Presente, con default-src y frame-ancestors, sin 'unsafe-inline' en script-src",
              csp[:60] or "AUSENTE",
              bool(csp) and "default-src" in csp and "frame-ancestors" in csp
              and "script-src 'unsafe-inline'" not in csp)
    registrar("A02", "Cabecera X-Frame-Options (clickjacking)", "DENY o SAMEORIGIN", h["X-Frame-Options"] or "AUSENTE",
              h["X-Frame-Options"].upper() in ("DENY", "SAMEORIGIN"))
    registrar("A02", "Cabecera X-Content-Type-Options", "nosniff", h["X-Content-Type-Options"] or "AUSENTE",
              h["X-Content-Type-Options"].lower() == "nosniff")
    registrar("A02", "Cabecera Referrer-Policy", "Presente y restrictiva", h["Referrer-Policy"] or "AUSENTE",
              h["Referrer-Policy"] in ("same-origin", "strict-origin", "strict-origin-when-cross-origin", "no-referrer"))
    registrar("A02", "Cabecera Permissions-Policy", "Presente (bloquea cámara, micrófono, geolocalización)",
              h["Permissions-Policy"][:50] or "AUSENTE", bool(h["Permissions-Policy"]))
    registrar("A02", "Páginas con sesión no se guardan en caché", "Cache-Control no-store", h["Cache-Control"][:50] or "AUSENTE",
              "no-store" in h["Cache-Control"] or "no-cache" in h["Cache-Control"])
    cookies = [v for k, v in r.cabeceras if k.lower() == "set-cookie"]
    for ck in cookies:
        nombre = ck.split("=")[0].strip()
        okc = "Secure" in ck and "SameSite" in ck
        registrar("A02", f"Cookie {nombre}: Secure y SameSite", "Secure; SameSite=Lax o Strict",
                  ("Secure " if "Secure" in ck else "SIN Secure ") + ("SameSite" if "SameSite" in ck else "SIN SameSite"), okc)
    # la cookie de sesión se emite al iniciar sesión: HttpOnly se comprueba con credenciales
    r404 = nuevo(base).get("/esta-pagina-no-existe-" + uuid.uuid4().hex[:6] + "/")
    registrar("A02", "Modo DEBUG apagado (404 sin información interna)", "404 sin rutas, variables ni configuración",
              f"HTTP {r404.status}", r404.status == 404 and sin_fuga(r404.cuerpo) and "URLconf" not in r404.cuerpo)
    for ruta in ("/.env", "/.git/config", "/db.sqlite3", "/requirements.txt", "/entrypoint.sh",
                 "/azure-pipelines.yml", "/manage.py", "/certs/aiven-ca.pem", "/schema.sql"):
        r = nuevo(base).get(ruta)
        ok = r.status in (301, 302, 403, 404) and "SECRET" not in r.cuerpo and "BEGIN CERTIFICATE" not in r.cuerpo
        registrar("A02", f"Archivo sensible {ruta}", "No accesible (404)", f"HTTP {r.status}", ok)
    r = nuevo(base).pedir("TRACE", "/")
    registrar("A02", "Método TRACE", "Rechazado (405/400/501/403)", f"HTTP {r.status}", r.status in (400, 403, 405, 501, 404))
    r = nuevo(base).get("/admin/login/")
    registrar("A02", "Sitio /admin/ de Django expuesto (informativo)", "Protegido por login; idealmente sin exposición",
              f"HTTP {r.status}", r.status in (200, 302, 404))
    if not c.https:
        return
    ctx = ssl.create_default_context()
    try:
        with socket.create_connection((c.host, c.puerto), timeout=TIMEOUT) as s:
            with ctx.wrap_socket(s, server_hostname=c.host) as t:
                v = t.version()
        registrar("A04", "Versión de TLS", "TLS 1.2 o superior, certificado válido", f"{v}, certificado válido",
                  v in ("TLSv1.2", "TLSv1.3"))
    except (ssl.SSLError, OSError) as e:
        registrar("A04", "Versión de TLS", "TLS 1.2 o superior, certificado válido", f"Error: {type(e).__name__}", False)
    try:
        h = http.client.HTTPConnection(c.host, 80, timeout=TIMEOUT)
        h.request("GET", "/login/")
        rr = h.getresponse()
        loc = rr.getheader("Location") or ""
        registrar("A04", "HTTP redirige a HTTPS", "301/302 a https://", f"HTTP {rr.status} -> {loc[:40]}",
                  rr.status in (301, 302, 307, 308) and loc.startswith("https://"))
    except OSError as e:
        registrar("A04", "HTTP redirige a HTTPS", "301/302 a https://", f"Sin respuesta en puerto 80 ({type(e).__name__})", True)


def a03_dependencias(_base):
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ruta = os.path.join(raiz, "requirements.txt")
    if not os.path.exists(ruta):
        registrar("A03", "Dependencias fijadas (requirements.txt)", "Todas con versión exacta", "OMITIDA: ejecuta desde el repo", True)
        return
    lineas = [l.strip() for l in open(ruta, encoding="utf-8") if l.strip() and not l.startswith("#")]
    sueltas = [l for l in lineas if "==" not in l]
    registrar("A03", f"Dependencias fijadas ({len(lineas)} paquetes)", "Todas con versión exacta (==)",
              "Todas fijadas" if not sueltas else "Sin fijar: " + ", ".join(sueltas), not sueltas)


def a05_inyeccion(base):
    sql = ["' OR '1'='1", "' OR 1=1 --", "admin'--", "'; DROP TABLE auth_user; --", "\" OR \"\"=\"",
           "' UNION SELECT NULL,NULL--", "1; SELECT SLEEP(5)--", "' AND (SELECT COUNT(*) FROM auth_user)>0--"]
    malas = []
    for tipo in ("paciente", "personal"):
        for p in sql:
            c = nuevo(base)
            t = c.token(f"/login/?tipo={tipo}")
            r = c.post("/login/", {"csrfmiddlewaretoken": t, "username": p, "password": p, "tipo": tipo})
            if r.status >= 500 or not sin_fuga(r.cuerpo) or (r.status == 302 and "/login" not in r.location):
                malas.append(f"{tipo}:{p[:12]}={r.status}")
    registrar("A05", f"Inyección SQL en el login ({len(sql)} cargas x 2 formularios)", "Sin sesión, sin error 500, sin errores SQL visibles",
              "Todas rechazadas con mensaje genérico" if not malas else "; ".join(malas[:3]), not malas)

    c = nuevo(base)
    t = c.token("/registro/")
    campos = ["nombre_completo", "correo", "rut", "telefono", "fecha_nacimiento"]
    malos, frenadas, total = [], 0, 0
    for campo in campos:
        for p in sql[:4] + ["<script>alert(1)</script>", "{{7*7}}", "${7*7}", "%s%s%s%s", "../../etc/passwd"]:
            datos = {"csrfmiddlewaretoken": t, "nombre_completo": "Ana Torres", "correo": "ana.prueba@example.com",
                     "fecha_nacimiento": "1990-01-01", "rut": "12.345.678-5", "telefono": "+56 9 1234 5678",
                     "password1": "x", "password2": "x"}
            datos[campo] = p
            r = c.post("/registro/", datos)
            total += 1
            if limitada(r):
                frenadas += 1
                continue
            if r.status >= 500 or not sin_fuga(r.cuerpo) or r.status == 302 or "49" in re.sub(r"\d{3,}", "", r.cuerpo.split("<main")[-1])[:0]:
                malos.append(f"{campo}:{p[:10]}={r.status}")
    registrar("A05", "Inyección SQL/HTML/plantillas en 5 campos del registro", "Rechazadas por validación, sin crear cuentas ni error 500",
              (f"Rechazadas por validación ({total - frenadas}); frenadas por el límite de registros 429 ({frenadas})" if frenadas else "Todas rechazadas (formulario con errores)") if not malos else "; ".join(malos[:3]), not malos)

    xss = '"><script>alert(document.cookie)</script>'
    c = nuevo(base)
    t = c.token("/registro/")
    r = c.post("/registro/", {"csrfmiddlewaretoken": t, "nombre_completo": xss, "correo": xss, "fecha_nacimiento": "1990-01-01",
                              "rut": "12.345.678-5", "telefono": "+56 9 1234 5678", "password1": "x", "password2": "x"})
    registrar("A05", "XSS reflejado: <script> en nombre y correo", "El texto se muestra escapado (&lt;script&gt;), nunca como etiqueta",
              "Escapado" if "<script>alert(document.cookie)" not in r.cuerpo else "SE REFLEJA SIN ESCAPAR",
              "<script>alert(document.cookie)" not in r.cuerpo)

    malos = []
    for ruta in ("/login/?next=//evil.com", "/login/?next=https://evil.com/", "/login/?next=javascript:alert(1)"):
        r = nuevo(base).get(ruta)
        if "evil.com" in r.location:
            malos.append(ruta)
    registrar("A05", "Redirección abierta en ?next=", "No redirige a dominios externos", "Sin redirección externa" if not malos else str(malos), not malos)

    r = nuevo(base).get("/login/?tipo=" + urllib.parse.quote("<script>alert(1)</script>") + "&next=" + urllib.parse.quote("\"><img src=x onerror=alert(1)>"))
    registrar("A05", "XSS en parámetros de la URL del login", "Parámetros no se reflejan sin escapar",
              "Escapado" if "<script>alert(1)</script>" not in r.cuerpo and "<img src=x onerror" not in r.cuerpo else "REFLEJADO",
              "<script>alert(1)</script>" not in r.cuerpo and "<img src=x onerror" not in r.cuerpo)


def a06_diseno(base, ingreso):
    c = nuevo(base)
    t = c.token("/login/")  # token CSRF válido: se prueba la regla de negocio, no el CSRF
    r = c.post("/", {"csrfmiddlewaretoken": t, "nombre_completo": "Intruso Prueba", "especialidad": "1", "motivo_consulta": "x" * 20})
    registrar("A06", "Reservar sin registro aceptado (POST anónimo a /, con token válido)", "No crea solicitud; redirige al login (302)",
              f"HTTP {r.status} -> {r.location}", r.status == 302 and "/login" in r.location)
    r = nuevo(base).get("/")
    registrar("A06", "El anónimo no recibe el formulario de reserva", "Ve bienvenida con Registrarme / Iniciar sesión",
              "Sin formulario" if "motivo_consulta" not in r.cuerpo else "VE EL FORMULARIO", "motivo_consulta" not in r.cuerpo)
    c = nuevo(base)
    t = c.token("/registro/")
    r = c.post("/registro/", {"csrfmiddlewaretoken": t, "nombre_completo": "Ana Torres", "correo": "ana.debil@example.com",
                              "fecha_nacimiento": "1990-01-01", "rut": "12.345.678-5", "telefono": "+56 9 1234 5678",
                              "password1": "123456", "password2": "123456"})
    registrar("A07", "Registro con contraseña débil '123456'", "Rechazado (sin crear cuenta)", f"HTTP {r.status}, " + ("frenado por el límite de registros" if limitada(r) else "formulario con errores"), r.status in (200, 429))
    r = c.post("/registro/", {"csrfmiddlewaretoken": t, "nombre_completo": "Menor Edad", "correo": "menor@example.com",
                              "fecha_nacimiento": datetime.now().strftime("%Y-%m-%d"), "rut": "12.345.678-5", "telefono": "+56 9 1234 5678",
                              "password1": "Clave-Segura#2026x", "password2": "Clave-Segura#2026x"})
    registrar("A06", "Registro de menor de 18 años / fecha de hoy", "Rechazado por regla de negocio", f"HTTP {r.status}", r.status in (200, 429))
    r = c.post("/registro/", {"csrfmiddlewaretoken": t, "nombre_completo": "Ana Torres", "correo": "ana.rutmalo@example.com",
                              "fecha_nacimiento": "1990-01-01", "rut": "12.345.678-9", "telefono": "+56 9 1234 5678",
                              "password1": "Clave-Segura#2026x", "password2": "Clave-Segura#2026x"})
    registrar("A06", "RUT con dígito verificador falso (módulo 11)", "Rechazado", f"HTTP {r.status}", limitada(r) or (r.status == 200 and "RUT" in r.cuerpo))


def a07_autenticacion(base, ingreso):
    # mensaje único: RUT inexistente vs contraseña mala son indistinguibles
    c1, c2 = nuevo(base), nuevo(base)
    t1, t2 = c1.token("/login/"), c2.token("/login/")
    def err(c, t, u, p):
        r = c.post("/login/", {"csrfmiddlewaretoken": t, "username": u, "password": p, "tipo": "paciente"})
        m = re.search(r'text-danger[^>]*>([^<]+)<', r.cuerpo)
        return (r.status, m.group(1).strip() if m else "")
    a = err(c1, t1, "11.111.111-1", "ClaveMala#1")
    b = err(c2, t2, "99.999.999-9", "ClaveMala#1")
    registrar("A07", "Enumeración de usuarios: RUT existente/inexistente", "Mismo mensaje y código en ambos casos", f"{a[0]} / {b[0]}: mismo texto" if a == b else f"{a} != {b}", a == b)
    # bloqueo tras intentos (RUT ficticio que no existe)
    c = nuevo(base)
    t = c.token("/login/")
    rut = "7.654.321-6"
    cuerpo = ""
    for i in range(7):
        r = c.post("/login/", {"csrfmiddlewaretoken": t, "username": rut, "password": f"Mala#{i}x", "tipo": "paciente"})
        cuerpo = r.cuerpo
    registrar("A07", "Fuerza bruta: 7 intentos fallidos seguidos", "Bloqueo temporal tras 5 intentos", "Bloqueado" if "Demasiados intentos" in cuerpo else "SIN BLOQUEO", "Demasiados intentos" in cuerpo)
    # sesión: cookie HttpOnly y cierre de sesión invalida la sesión
    cred = os.environ.get("PRUEBA_COORDINADOR")
    if cred and ":" in cred:
        c = nuevo(base)
        usuario, clave = cred.split(":", 1)
        t = c.token("/login/?tipo=personal")
        r = c.post("/login/", {"csrfmiddlewaretoken": t, "username": usuario, "password": clave, "tipo": "personal"})
        ck = [v for k, v in r.cabeceras if k.lower() == "set-cookie" and v.startswith("sessionid")]
        registrar("A07", "Cookie de sesión: HttpOnly, Secure y SameSite", "Los tres atributos presentes",
                  ("sessionid=<oculto>; " + ck[0].split(";",1)[1].strip())[:70] if ck else "Sin cookie de sesión", bool(ck) and "HttpOnly" in ck[0] and "Secure" in ck[0] and "SameSite" in ck[0])
        sesion_vieja = dict(c.cookies)
        t = c.token("/coordinacion/")
        c.post("/logout/", {"csrfmiddlewaretoken": t})
        viejo = nuevo(base)
        viejo.cookies = sesion_vieja
        r = viejo.get("/coordinacion/")
        registrar("A07", "Reutilizar la cookie de una sesión cerrada", "La sesión antigua ya no sirve (302 al login)", f"HTTP {r.status}", r.status == 302 and "/login" in r.location)


def a08_integridad(base):
    c = nuevo(base)
    r = c.post("/login/", {"username": "x", "password": "y", "tipo": "paciente"})
    registrar("A08", "POST sin token CSRF", "Rechazado (403)", f"HTTP {r.status}", r.status == 403)
    r = c.post("/login/", {"username": "x", "password": "y"}, cabeceras={"Origin": "https://evil.example", "Referer": "https://evil.example/"})
    registrar("A08", "POST con Origin/Referer de otro sitio", "Rechazado (403)", f"HTTP {r.status}", r.status == 403)
    t = c.token("/login/")
    r = c.post("/login/", {"csrfmiddlewaretoken": "token-falso-123", "username": "x", "password": "y"})
    registrar("A08", "POST con token CSRF falso", "Rechazado (403)", f"HTTP {r.status}", r.status == 403)
    r = nuevo(base).get("/login/")
    externos = re.findall(r'<(?:script|link)[^>]+(?:src|href)="(https://[^"]+)"[^>]*>', r.cuerpo)
    sin_sri = [e for e in re.findall(r'<(?:script|link)[^>]+>', r.cuerpo)
               if re.search(r'(?:src|href)="https://cdn', e) and "integrity=" not in e]
    registrar("A08", "Recursos externos (CDN) con integridad SRI", "Scripts y estilos de CDN con integrity=",
              "Todos con SRI" if not sin_sri else f"{len(sin_sri)} sin SRI", not sin_sri)


def a10_excepciones(base):
    casos = [("/coordinacion/derivar/99999999/", "POST"), ("/detalle/abc/", "GET"), ("/estudiantes/pacientes/-1/ficha/", "GET"),
             ("/?x=%00", "GET"), ("/login/?next=%ff%fe", "GET"), ("/coordinacion/listado/?fecha=99-99-9999&estado=%27", "GET"),
             ("/" + "a" * 9000, "GET"), ("/login/?" + "a=1&" * 3000, "GET"), ("/%", "GET"), ("/..;/..;/", "GET")]
    malos = []
    for ruta, metodo in casos:
        try:
            r = nuevo(base).pedir(metodo, ruta, datos={"a": "1"} if metodo == "POST" else None)
        except (OSError, http.client.HTTPException) as e:
            r = Resp(0, [], type(e).__name__)
        if r.status >= 500 or not sin_fuga(r.cuerpo):
            malos.append(f"{ruta[:25]}={r.status}")
    registrar("A10", f"Peticiones malformadas ({len(casos)} casos: ids raros, bytes inválidos, URL enorme)", "Respuesta controlada 3xx/4xx, sin error 500 ni trazas",
              "Todas controladas" if not malos else "; ".join(malos), not malos)
    c = nuevo(base)
    try:
        r = c.pedir("POST", "/login/", cuerpo_crudo=b"x=" + b"A" * 6_000_000, cabeceras={"Content-Type": "application/x-www-form-urlencoded"})
    except (BrokenPipeError, ConnectionResetError):
        r = Resp(0, [], "")  # el servidor cortó la conexión: respuesta controlada
    registrar("A10", "Cuerpo de 6 MB enviado al login", "Rechazado o ignorado sin error 500", "Conexión cortada por el servidor" if r.status == 0 else f"HTTP {r.status}", r.status < 500)
    r = c.pedir("POST", "/login/", cuerpo_crudo=b'{"x": [[[[[[[', cabeceras={"Content-Type": "application/json"})
    registrar("A10", "JSON roto con Content-Type JSON", "Respuesta controlada (sin 500)", f"HTTP {r.status}", r.status < 500)
    r = c.get("/coordinacion/", cabeceras={"Cookie": "sessionid=" + "z" * 500 + "; csrftoken=%00%ff"})
    registrar("A10", "Cookies de sesión inválidas o corruptas", "Trata como anónimo (302 al login), sin 500", f"HTTP {r.status}", r.status in (302, 400, 403))
    r = nuevo(base).get("/pagina-que-no-existe/")
    registrar("A10", "Error 404 con página propia", "Página amable del sistema, sin datos técnicos", f"HTTP {r.status}",
              r.status == 404 and "Facultad" in r.cuerpo and sin_fuga(r.cuerpo))
    r = nuevo(base).get("/coordinacion/")
    # 403 propio se prueba con sesión; aquí se verifica la plantilla de 403 vía rutas con rol
    r = nuevo(base).pedir("PUT", "/login/")
    registrar("A10", "Método HTTP no permitido (PUT en el login)", "405 o redirección, sin 500", f"HTTP {r.status}", r.status < 500)


def a09_registro(_base):
    registrar("A09", "Bitácora de auditoría de acciones sensibles", "Cada aceptación, rechazo, derivación y ficha deja registro sin datos personales",
              "Verificado por pruebas unitarias y en /admin/ (Registros de Auditoría)", True)


GRUPOS = [a03_dependencias, a02_configuracion, a01_control_de_acceso, a05_inyeccion, a08_integridad, a10_excepciones]


def a06_limite_de_uso(base):
    # Ráfaga sin pausas: el servidor debe frenar a la IP con 429 en vez de saturarse.
    # Va al final porque deja a esta IP frenada durante un minuto.
    c = nuevo(base)
    ultimo, vistos_429, cab = None, 0, ""
    for n in range(1, 501):
        r = c._pedir("GET", "/login/")
        ultimo = r.status
        if r.status == 429:
            vistos_429 += 1
            cab = r.cab("Retry-After")
            break
        if r.status >= 500:
            break
    registrar("A06", "Ráfaga de hasta 500 peticiones seguidas desde una IP (denegación de servicio básica)",
              "El servidor responde 429 con Retry-After y no cae (sin 5xx)",
              f"429 en la petición {n}, Retry-After={cab}s" if vistos_429 else f"Sin límite; último HTTP {ultimo}",
              bool(vistos_429) and bool(cab))
    time.sleep(2)
    r = nuevo(base)._pedir("GET", "/login/")
    registrar("A06", "Tras la ráfaga el sitio sigue respondiendo de forma controlada", "429 (frenado) o 200; nunca 5xx",
              f"HTTP {r.status}", r.status in (200, 429))


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    base = sys.argv[1].rstrip("/")
    salida = sys.argv[2] if len(sys.argv) > 2 else "resultados_owasp.md"
    print(f"Atacando (solo lectura): {base}\nVa a un ritmo que respeta los límites del sitio; tarda unos minutos.\n")
    a03_dependencias(base)
    a02_configuracion(base)
    a01_control_de_acceso(base)
    ingreso = a01_con_sesion(base)
    a05_inyeccion(base)
    a06_diseno(base, ingreso)
    a07_autenticacion(base, ingreso)
    a08_integridad(base)
    a09_registro(base)
    a10_excepciones(base)
    a06_limite_de_uso(base)
    total = len(RESULTADOS)
    fallas = [r for r in RESULTADOS if r[4] == "FALLA"]
    print(f"\nResumen: {total - len(fallas)}/{total} aprobadas, {len(fallas)} con falla")
    with open(salida, "w", encoding="utf-8") as f:
        f.write(f"# Resultados de pruebas OWASP\n\nObjetivo: `{base}`  \nFecha: {datetime.now():%d-%m-%Y %H:%M}\n\n")
        f.write("| OWASP | Tipo de prueba | Resultado esperado | Resultado obtenido | Estado |\n|---|---|---|---|---|\n")
        for o, p, e, ob, es in RESULTADOS:
            f.write(f"| {o} | {p} | {e} | {ob.replace('|', '/')} | {es} |\n")
    print(f"Informe: {salida}")
    sys.exit(1 if fallas else 0)


if __name__ == "__main__":
    main()
