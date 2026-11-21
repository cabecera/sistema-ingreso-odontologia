from unittest import mock

from django.core.mail import EmailMessage
from django.test import SimpleTestCase, override_settings

from seguridad.email_backend import BrevoEmailBackend

CLAVE_FALSA = "xkeysib-xxx"


def mensaje():
    return EmailMessage(
        "Tu registro fue aprobado", "Ingresa con tu RUT.", "Facultad <ok@example.com>", ["paciente@example.com"]
    )


def respuesta(estado):
    r = mock.Mock(status=estado)
    r.read.return_value = b"{}"
    return r


@override_settings(BREVO_API_KEY=CLAVE_FALSA)
class BrevoBackendTests(SimpleTestCase):

    def enviar(self, estado=201, **kw):
        with mock.patch("seguridad.email_backend.http.client.HTTPSConnection") as conexion:
            conexion.return_value.getresponse.return_value = respuesta(estado)
            resultado = BrevoEmailBackend(**kw).send_messages([mensaje()])
        return resultado, conexion

    def test_envia_por_https_a_brevo_con_la_clave_en_el_encabezado(self):
        resultado, conexion = self.enviar()
        self.assertEqual(resultado, 1)
        self.assertEqual(conexion.call_args.args[0], "api.brevo.com")
        metodo, ruta = conexion.return_value.request.call_args.args[:2]
        self.assertEqual((metodo, ruta), ("POST", "/v3/smtp/email"))
        kwargs = conexion.return_value.request.call_args.kwargs
        self.assertEqual(kwargs["headers"]["api-key"], CLAVE_FALSA)
        self.assertNotIn(CLAVE_FALSA, kwargs["body"])  # la clave no va en el cuerpo
        self.assertIn('"email": "paciente@example.com"', kwargs["body"])
        self.assertIn('"name": "Facultad"', kwargs["body"])
        conexion.return_value.close.assert_called_once()

    def test_un_error_de_brevo_se_propaga_o_se_silencia_segun_fail_silently(self):
        with self.assertRaises(RuntimeError):
            self.enviar(estado=401)
        resultado, _ = self.enviar(estado=401, fail_silently=True)
        self.assertEqual(resultado, 0)

    def test_un_fallo_de_red_no_se_traga_en_silencio_por_defecto(self):
        with mock.patch("seguridad.email_backend.http.client.HTTPSConnection") as conexion:
            conexion.return_value.request.side_effect = OSError("sin red")
            with self.assertRaises(OSError):
                BrevoEmailBackend().send_messages([mensaje()])

    def test_el_log_indica_el_estado_y_el_codigo_de_brevo(self):
        with mock.patch("seguridad.email_backend.http.client.HTTPSConnection") as conexion:
            r = respuesta(401)
            r.read.return_value = b'{"code": "unauthorized", "message": "IP no autorizada paciente@example.com"}'
            conexion.return_value.getresponse.return_value = r
            with self.assertLogs("seguridad.email_backend", "WARNING") as log:
                BrevoEmailBackend(fail_silently=True).send_messages([mensaje()])
        texto = " ".join(log.output)
        self.assertIn("401", texto)
        self.assertIn("unauthorized", texto)
        self.assertNotIn("paciente@example.com", texto)  # el mensaje libre de Brevo no se copia

    def test_el_log_de_error_no_incluye_correo_ni_clave(self):
        with self.assertLogs("seguridad.email_backend", "WARNING") as log:
            self.enviar(estado=500, fail_silently=True)
        texto = " ".join(log.output)
        self.assertNotIn("paciente@example.com", texto)
        self.assertNotIn(CLAVE_FALSA, texto)

    @override_settings(BREVO_API_KEY="")
    def test_sin_clave_no_envia_nada(self):
        with self.assertRaises(RuntimeError):
            BrevoEmailBackend().send_messages([mensaje()])
        self.assertEqual(BrevoEmailBackend(fail_silently=True).send_messages([mensaje()]), 0)
