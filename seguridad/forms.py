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
#   Se guarda en el caché del servidor, sin datos personales (solo un hash).
# ============================================
import hashlib

from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.core.cache import cache
from django.core.exceptions import ValidationError

from pacientes.models import PerfilPaciente
from pacientes.rut_login import hash_rut
from pacientes.validators import limpiar_rut

PACIENTE = "paciente"
PERSONAL = "personal"
MAX_INTENTOS = 5
BLOQUEO_SEGUNDOS = 600
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

    def _clave_bloqueo(self, identificador):
        base = limpiar_rut(identificador) if self.tipo_actual == PACIENTE else identificador.strip().lower()
        return "login:" + hashlib.sha256(f"{self.tipo_actual}:{base}".encode()).hexdigest()

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
        clave = self._clave_bloqueo(identificador)
        if cache.get(clave, 0) >= MAX_INTENTOS:
            raise ValidationError(
                "Demasiados intentos fallidos. Espera 10 minutos e inténtalo de nuevo.",
                code="bloqueado",
            )
        if self.tipo_actual == PACIENTE:
            self.cleaned_data["username"] = self._usuario_del_paciente(identificador)
        try:
            resultado = super().clean()
        except ValidationError:
            cache.add(clave, 0, BLOQUEO_SEGUNDOS)
            try:
                cache.incr(clave)
            except ValueError:  # la clave venció justo ahora
                cache.set(clave, 1, BLOQUEO_SEGUNDOS)
            raise
        cache.delete(clave)
        return resultado
