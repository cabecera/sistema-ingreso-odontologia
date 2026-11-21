# ============================================
# Envío de correos por HTTPS (Brevo, plan gratuito)
# --------------------------------------------
# Render Free bloquea los puertos SMTP (25, 465, 587), pero deja salir HTTPS.
# Este backend envía por la API de Brevo (300 correos/día gratis) usando solo
# la biblioteca estándar. Se activa con la variable de entorno BREVO_API_KEY;
# sin ella, el sistema sigue imprimiendo el correo en el log (backend console).
# - La clave solo viaja en el encabezado de la petición y nunca se registra.
# - Solo se conecta a api.brevo.com por HTTPS, con verificación de certificado.
# - Un fallo no rompe la operación del usuario: los llamadores ya capturan la
#   excepción y escriben un aviso sin datos personales.
# ============================================
import http.client
import json
import logging
from email.utils import parseaddr

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)

HOST = "api.brevo.com"
RUTA = "/v3/smtp/email"
TIMEOUT_SEGUNDOS = 10


class BrevoEmailBackend(BaseEmailBackend):

    def send_messages(self, email_messages):
        clave = getattr(settings, "BREVO_API_KEY", "")
        if not clave:
            if not self.fail_silently:
                raise RuntimeError("Falta BREVO_API_KEY para enviar correos.")
            return 0
        enviados = 0
        for mensaje in email_messages:
            try:
                self._enviar(clave, mensaje)
                enviados += 1
            except Exception:  # noqa: BLE001 - se informa solo el tipo de error, sin datos personales
                logger.warning("No se pudo enviar el correo por Brevo.")
                if not self.fail_silently:
                    raise
        return enviados

    def _enviar(self, clave, mensaje):
        nombre, direccion = parseaddr(mensaje.from_email or settings.DEFAULT_FROM_EMAIL)
        remitente = {"email": direccion}
        if nombre:
            remitente["name"] = nombre
        cuerpo = {
            "sender": remitente,
            "to": [{"email": destino} for destino in mensaje.to],
            "subject": mensaje.subject,
            "textContent": mensaje.body,
        }
        conexion = http.client.HTTPSConnection(HOST, timeout=TIMEOUT_SEGUNDOS)
        try:
            conexion.request(
                "POST", RUTA, body=json.dumps(cuerpo),
                headers={
                    "api-key": clave,
                    "content-type": "application/json",
                    "accept": "application/json",
                },
            )
            respuesta = conexion.getresponse()
            respuesta.read()
        finally:
            conexion.close()
        if respuesta.status not in (200, 201, 202):
            raise RuntimeError(f"Brevo respondió con el estado {respuesta.status}.")
