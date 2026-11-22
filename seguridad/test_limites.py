from datetime import date

from django.contrib.auth.models import Group, User
from django.core.cache import cache
from django.test import TestCase, override_settings

from pacientes.models import PerfilPaciente
from seguridad.limites import ip_cliente

CLAVE = "Clave-Segura#2026x"
RUT = "12.345.678-5"


def paciente():
    u = User.objects.create_user("p0a1b2c3d4e5", password=CLAVE)
    PerfilPaciente.objects.create(
        usuario=u, nombre_completo="Paciente Limite", fecha_nacimiento=date(1990, 1, 1),
        rut=RUT, telefono="+56 9 1234 5678", estado="ACEPTADO",
    )


def ip(n):
    return {"REMOTE_ADDR": "10.0.0.%d" % n}


@override_settings(LIMITES_ACTIVOS=True, LIMITE_GENERAL_POR_MINUTO=10, LIMITE_POST_POR_MINUTO=5,
                   LIMITE_LOGIN_POR_MINUTO=100, LIMITE_REGISTRO_POR_HORA=3, LIMITES_SALTOS_PROXY=1)
class LimitesPorIpTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_demasiadas_peticiones_dan_429_y_otra_ip_sigue_normal(self):
        codigos = [self.client.get("/login/", secure=True, **ip(1)).status_code for _ in range(12)]
        self.assertEqual(codigos[:10], [200] * 10)
        self.assertEqual(codigos[10:], [429, 429])
        self.assertEqual(self.client.get("/login/", secure=True, **ip(2)).status_code, 200)

    def test_la_respuesta_429_trae_retry_after_y_no_datos_tecnicos(self):
        for _ in range(10):
            self.client.get("/login/", secure=True, **ip(3))
        r = self.client.get("/login/", secure=True, **ip(3))
        self.assertEqual(r.status_code, 429)
        self.assertIn("Retry-After", r)
        self.assertNotIn(b"Traceback", r.content)

    def test_los_archivos_estaticos_no_cuentan(self):
        for _ in range(30):
            self.client.get("/static/no-existe.css", secure=True, **ip(4))
        self.assertEqual(self.client.get("/login/", secure=True, **ip(4)).status_code, 200)

    def test_el_registro_se_limita_por_hora(self):
        codigos = [self.client.post("/registro/", {}, secure=True, **ip(5)).status_code for _ in range(5)]
        # los 3 primeros llegan a la vista (formulario con errores, 200 o 403 por CSRF); luego 429
        self.assertEqual(codigos[3:], [429, 429])
        self.assertNotIn(429, codigos[:3])

    def test_los_posts_tienen_tope_propio(self):
        codigos = [self.client.post("/login/", {}, secure=True, **ip(6)).status_code for _ in range(7)]
        self.assertEqual(codigos[5:], [429, 429])

    def test_la_ip_falsa_escrita_por_el_cliente_no_evade_el_limite(self):
        # El proxy agrega la IP real al final; lo que el cliente escribe va antes.
        for i in range(12):
            r = self.client.get("/login/", secure=True, REMOTE_ADDR="10.9.9.9",
                                HTTP_X_FORWARDED_FOR="1.2.3.%d, 8.8.8.8" % i)
        self.assertEqual(r.status_code, 429)

    def test_ip_cliente_cuenta_los_saltos_desde_el_final(self):
        from django.test import RequestFactory
        r = RequestFactory().get("/", HTTP_X_FORWARDED_FOR="1.1.1.1, 2.2.2.2, 3.3.3.3")
        with override_settings(LIMITES_SALTOS_PROXY=2):
            self.assertEqual(ip_cliente(r), "2.2.2.2")
        with override_settings(LIMITES_SALTOS_PROXY=1):
            self.assertEqual(ip_cliente(r), "3.3.3.3")
        sin = RequestFactory().get("/", REMOTE_ADDR="7.7.7.7")
        self.assertEqual(ip_cliente(sin), "7.7.7.7")


@override_settings(LIMITES_ACTIVOS=False)
class BloqueoLoginPorParTests(TestCase):
    def setUp(self):
        cache.clear()
        paciente()

    def entrar(self, clave, direccion):
        return self.client.post("/login/", {"username": RUT, "password": clave, "tipo": "paciente"},
                                secure=True, **ip(direccion))

    def test_un_atacante_no_puede_bloquear_a_la_victima_desde_otra_ip(self):
        for _ in range(8):
            r = self.entrar("mala", 50)
        self.assertIn("Demasiados intentos", " ".join(r.context["form"].non_field_errors()))
        # la víctima, desde su propia IP, entra con normalidad
        r = self.entrar(CLAVE, 51)
        self.assertEqual(r.status_code, 302)

    def test_el_atacante_si_queda_bloqueado_aun_con_la_clave_correcta(self):
        for _ in range(5):
            self.entrar("mala", 52)
        r = self.entrar(CLAVE, 52)
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_adivinar_desde_muchas_ip_tiene_tope_por_identificador(self):
        for n in range(60, 95):
            self.entrar("mala", n)
        r = self.entrar(CLAVE, 99)
        self.assertEqual(r.status_code, 200)  # tope global del identificador alcanzado
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_una_ip_no_puede_probar_muchas_cuentas(self):
        for n in range(45):
            self.client.post("/login/", {"username": "00.000.%03d-0" % n, "password": "x", "tipo": "paciente"},
                             secure=True, **ip(70))
        r = self.entrar(CLAVE, 70)
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)


class AjustesDeResilienciaTests(TestCase):
    def test_tope_de_cuerpo_de_peticion(self):
        from django.conf import settings
        self.assertLessEqual(settings.DATA_UPLOAD_MAX_MEMORY_SIZE, 200 * 1024)
        self.assertEqual(settings.DATA_UPLOAD_MAX_NUMBER_FILES, 0)

    def test_cuerpo_enorme_se_rechaza_sin_error_500(self):
        r = self.client.post("/login/", {"username": "a", "password": "x" * 300_000}, secure=True)
        self.assertLess(r.status_code, 500)


@override_settings(LIMITES_ACTIVOS=False)
class BloqueoCompartidoEntreProcesosTests(TestCase):
    """Gunicorn usa varios procesos con memoria propia: el bloqueo no debe depender de ella."""

    def setUp(self):
        paciente()

    def test_el_bloqueo_llega_aunque_la_memoria_del_proceso_se_reinicie_en_cada_intento(self):
        for _ in range(5):
            cache.clear()  # simula que el intento cayó en otro proceso, con memoria vacía
            self.client.post("/login/", {"username": RUT, "password": "mala", "tipo": "paciente"},
                             secure=True, **ip(80))
        cache.clear()
        r = self.client.post("/login/", {"username": RUT, "password": CLAVE, "tipo": "paciente"},
                             secure=True, **ip(80))
        self.assertEqual(r.status_code, 200)
        self.assertIn("Demasiados intentos", " ".join(r.context["form"].non_field_errors()))

    def test_los_contadores_estan_en_la_base_de_datos(self):
        from django.conf import settings
        self.assertIn("DatabaseCache", settings.CACHES["bloqueos"]["BACKEND"])


class IpRealTests(TestCase):
    def test_usa_la_ip_del_cdn_aunque_la_cadena_de_proxies_cambie(self):
        from django.test import RequestFactory
        f = RequestFactory()
        a = f.get("/", HTTP_CF_CONNECTING_IP="190.5.48.149", HTTP_X_FORWARDED_FOR="9.9.9.9, 172.70.1.1, 10.0.0.1")
        b = f.get("/", HTTP_CF_CONNECTING_IP="190.5.48.149", HTTP_X_FORWARDED_FOR="9.9.9.9, 162.158.2.2, 10.0.0.2")
        self.assertEqual(ip_cliente(a), "190.5.48.149")
        self.assertEqual(ip_cliente(a), ip_cliente(b))

    def test_sin_cdn_cuenta_desde_el_final_y_valida_el_formato(self):
        from django.test import RequestFactory
        f = RequestFactory()
        r = f.get("/", HTTP_X_FORWARDED_FOR="falsa, 190.5.48.149, 172.70.1.1, 10.0.0.1")
        with override_settings(LIMITES_SALTOS_PROXY=3):
            self.assertEqual(ip_cliente(r), "190.5.48.149")
        basura = f.get("/", HTTP_CF_CONNECTING_IP="no-es-ip", REMOTE_ADDR="7.7.7.7")
        self.assertEqual(ip_cliente(basura), "7.7.7.7")

    @override_settings(LIMITES_ACTIVOS=True, LIMITE_GENERAL_POR_MINUTO=1000)
    def test_el_diagnostico_esta_apagado_por_defecto_y_se_puede_encender(self):
        r = self.client.get("/login/", secure=True, HTTP_CF_CONNECTING_IP="1.2.3.4")
        self.assertNotIn("X-Diag-Ip", r)
        with override_settings(DIAGNOSTICO_IP=True):
            r = self.client.get("/login/", secure=True, HTTP_CF_CONNECTING_IP="1.2.3.4")
        self.assertEqual(r["X-Diag-Ip"], "1.2.3.4")
