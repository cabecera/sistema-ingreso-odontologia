# ============================================
# Inicio de sesión: pacientes con RUT, personal con usuario
# --------------------------------------------
# - Paciente: ingresa con su RUT. Se busca por el índice ciego (rut_hash) y se
#   autentica con el usuario interno; el RUT nunca es nombre de usuario en claro.
# - Personal (Coordinador, Estudiante, Super Administrador): usuario restringido.
# - Mensaje de error único: no revela si el RUT/usuario existe, si la cuenta
#   está pendiente o si la contraseña fue la equivocada.
# - Bloqueo: tras 5 fallos seguidos para un mismo identificador, 10 minutos sin
#   poder intentar (frena la adivinanza de contraseñas; el RUT no es secreto).
#   El contador es por IP + identificador: quien falla desde su conexión no puede
#   bloquear la cuenta de otra persona que entra desde otra IP.
#   Se guarda en el caché del servidor, sin datos personales (solo un hash).
# ============================================
import hashlib

from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError
from django.core.validators import MaxLengthValidator

from pacientes.models import PerfilPaciente
from pacientes.rut_login import hash_rut
from pacientes.validators import limpiar_rut
from seguridad.limites import bloqueos, contar, ip_cliente, superado

PACIENTE = "paciente"
PERSONAL = "personal"
CLAVE_LOGIN_MAXIMO = 128
MAX_INTENTOS = 5
BLOQUEO_SEGUNDOS = 600
# Además del bloqueo por IP + identificador (5 fallos), hay dos topes más altos:
# - por identificador desde cualquier IP: frena la adivinanza repartida entre
#   muchas IP, sin que unos pocos intentos ajenos puedan dejar fuera a un usuario;
# - por IP con cualquier identificador: frena probar muchas cuentas desde una IP.
MAX_INTENTOS_IDENTIFICADOR = 30
MAX_INTENTOS_IP = 40
# Usuario inexistente: Django igual calcula un hash falso y así la respuesta
# tarda lo mismo que con un usuario real.
USUARIO_INEXISTENTE = "-"


class LoginForm(AuthenticationForm):
    tipo = forms.ChoiceField(
        choices=[(PACIENTE, "Paciente"), (PERSONAL, "Personal")],
        widget=forms.HiddenInput,
        required=False,
        initial=PACIENTE,
    )

    @property
    def tipo_actual(self):
        valor = self.data.get("tipo") if self.is_bound else self.initial.get("tipo")
        return PERSONAL if valor == PERSONAL else PACIENTE

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        campo = self.fields["username"]
        campo.widget.attrs["class"] = "form-control"
        self.fields["password"].widget.attrs["class"] = "form-control"
        # Tope generoso: evita enviar textos enormes para que el servidor los procese.
        self.fields["password"].widget.attrs["maxlength"] = str(CLAVE_LOGIN_MAXIMO)
        self.fields["password"].validators.append(MaxLengthValidator(CLAVE_LOGIN_MAXIMO))
        if self.tipo_actual == PACIENTE:
            campo.label = "RUT"
            campo.max_length = 14
            campo.widget.attrs.update(
                {"placeholder": "12.345.678-5", "maxlength": "14", "autocomplete": "username"}
            )
            mensaje = (
                "RUT o contraseña incorrectos. Si te registraste hace poco, "
                "tu cuenta puede estar pendiente de aprobación."
            )
        else:
            campo.label = "Usuario"
            campo.widget.attrs.update({"maxlength": "150", "autocomplete": "username"})
            mensaje = "Usuario o contraseña incorrectos."
        self.error_messages = {**self.error_messages, "invalid_login": mensaje}

    def _base(self, identificador):
        base = limpiar_rut(identificador) if self.tipo_actual == PACIENTE else identificador.strip().lower()
        return f"{self.tipo_actual}:{base}"

    def _ip(self):
        solicitud = getattr(self, "request", None)
        return ip_cliente(solicitud) if solicitud is not None else "sin-ip"

    def _claves_bloqueo(self, identificador):
        base = self._base(identificador)

        def h(*partes):
            return "login:" + hashlib.sha256(":".join(partes).encode()).hexdigest()

        ip = self._ip()
        return (
            (h("par", ip, base), MAX_INTENTOS),
            (h("id", base), MAX_INTENTOS_IDENTIFICADOR),
            (h("ip", ip), MAX_INTENTOS_IP),
        )

    def _usuario_del_paciente(self, identificador):
        valor = hash_rut(identificador)
        perfil = (
            PerfilPaciente.objects.select_related("usuario").filter(rut_hash=valor).first()
            if valor else None
        )
        return perfil.usuario.get_username() if perfil else USUARIO_INEXISTENTE

    def clean(self):
        identificador = (self.cleaned_data.get("username") or "").strip()
        if not identificador or not self.cleaned_data.get("password"):
            return self.cleaned_data
        claves = self._claves_bloqueo(identificador)
        almacen = bloqueos()
        if any(superado(clave, tope, almacen) for clave, tope in claves):
            raise ValidationError(
                "Demasiados intentos fallidos. Espera 10 minutos e inténtalo de nuevo.",
                code="bloqueado",
            )
        if self.tipo_actual == PACIENTE:
            self.cleaned_data["username"] = self._usuario_del_paciente(identificador)
        try:
            resultado = super().clean()
        except ValidationError:
            for clave, _tope in claves:
                contar(clave, BLOQUEO_SEGUNDOS, almacen)
            raise
        almacen.delete(claves[0][0])  # entrada correcta: se limpia el contador de este par
        return resultado
