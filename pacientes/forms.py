# ============================================
# Task 30: Crear el formulario público y su página
# Issue padre: REQ-01 (Registro público de solicitud)
# --------------------------------------------
# Formulario que completa el paciente (sin cuenta). Lineamiento
# del profesor: los campos no pueden aceptar textos de largo
# ilimitado. Los límites se definen una sola vez (LIMITES_TEXTO)
# y se aplican en el navegador (maxlength) y en el servidor.
# ============================================

import re
import unicodedata
from datetime import date

from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.validators import MaxLengthValidator

from administracion.models import Especialidad

from .models import PerfilPaciente, Solicitud
from .validators import (
    EDAD_MINIMA_REGISTRO,
    limites_fecha_nacimiento,
    validar_mayor_de_edad,
)

# ============================================
# Task 55: Reforzar las validaciones de todos los formularios
# Issue padre: REQ-10 (Validación y sanitización de entradas)
# --------------------------------------------
# Se agrega validación en el servidor para:
#   - nombre_completo: solo letras (con tildes/ñ), espacios, guion,
#     apóstrofe y punto; largo mínimo; espacios repetidos normalizados.
#   - motivo_consulta: largo mínimo, para que no llegue "x" o "..." .
#   - textos largos: se eliminan caracteres de control invisibles.
# Esto se suma a lo que ya existía (RUT, fecha, teléfono, largos máximos).
# ============================================

NOMBRE_LARGO_MINIMO = 3
NOMBRE_LARGO_MAXIMO = 100
MOTIVO_LARGO_MINIMO = 10
CARACTERES_NOMBRE_PERMITIDOS = " -"
PASSWORD_LARGO_MAXIMO = 50


def limpiar_texto(valor):
    """Quita caracteres de control (categoría Unicode Cc) salvo salto de
    línea y tabulación, y unifica los saltos de línea a \\n."""
    valor = valor.replace("\r\n", "\n").replace("\r", "\n")
    return "".join(
        ch for ch in valor
        if ch in "\n\t" or unicodedata.category(ch) != "Cc"
    ).strip()


LIMITES_TEXTO = {
    "motivo_consulta": 500,
    "experiencia_previa": 500,
    "antecedentes_personales": 1000,
    "antecedentes_familiares": 1000,
}


def normalizar_nombre(valor):
    """Normaliza espacios y exige solo letras (con tildes y ñ), espacios y guion.
    Rechaza números, símbolos y etiquetas HTML."""
    nombre = " ".join(valor.split())
    if len(nombre) < NOMBRE_LARGO_MINIMO:
        raise forms.ValidationError(
            f"El nombre debe tener al menos {NOMBRE_LARGO_MINIMO} caracteres."
        )
    if len(nombre) > NOMBRE_LARGO_MAXIMO:
        raise forms.ValidationError(
            f"El nombre no puede tener más de {NOMBRE_LARGO_MAXIMO} caracteres."
        )
    if not all(ch.isalpha() or ch in CARACTERES_NOMBRE_PERMITIDOS for ch in nombre):
        raise forms.ValidationError(
            "El nombre solo puede tener letras, espacios y guion (sin números ni símbolos)."
        )
    if sum(ch.isalpha() for ch in nombre) < 2:
        raise forms.ValidationError("Ingresa un nombre válido.")
    return nombre


def normalizar_telefono(valor):
    """Teléfono chileno: solo números, espacios y un + inicial.
    9 dígitos ("9 1234 5678") u 11 con el código del país ("+56 9 1234 5678")."""
    telefono = " ".join(valor.split())
    if not re.fullmatch(r"\+?[0-9 ]+", telefono):
        raise forms.ValidationError(
            "Usa solo números, espacios y un + al inicio (sin letras ni otros símbolos)."
        )
    digitos = re.sub(r"\D", "", telefono)
    if len(digitos) == 11 and digitos.startswith("56"):
        return telefono
    if len(digitos) == 9:
        return telefono
    raise forms.ValidationError(
        "Ingresa un teléfono chileno de 9 dígitos, o de 11 con el +56 (ej: +56 9 1234 5678)."
    )


class SolicitudForm(forms.ModelForm):
    class Meta:
        model = Solicitud
        fields = [
            "nombre_completo",
            "fecha_nacimiento",
            "rut",
            "telefono",
            "especialidad",
            "motivo_consulta",
            "experiencia_previa",
            "antecedentes_personales",
            "antecedentes_familiares",
        ]
        widgets = {
            # type="date" muestra un calendario; format ISO para que el
            # valor se vuelva a mostrar bien si el formulario tiene errores.
            "fecha_nacimiento": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "rut": forms.TextInput(attrs={"placeholder": "12.345.678-5"}),
            "telefono": forms.TextInput(attrs={"type": "tel", "placeholder": "+56 9 1234 5678", "maxlength": "16"}),
            "motivo_consulta": forms.Textarea(attrs={"rows": 3}),
            "experiencia_previa": forms.Textarea(attrs={"rows": 3}),
            "antecedentes_personales": forms.Textarea(attrs={"rows": 4}),
            "antecedentes_familiares": forms.Textarea(attrs={"rows": 4}),
        }

    # Datos personales que, con sesión iniciada, salen del perfil del paciente
    # y NO se piden de nuevo (así nadie puede reservar con datos ajenos).
    CAMPOS_DEL_PERFIL = ("nombre_completo", "fecha_nacimiento", "rut", "telefono")

    def __init__(self, *args, perfil=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.perfil = perfil
        if perfil is not None:
            for nombre in self.CAMPOS_DEL_PERFIL:
                del self.fields[nombre]

        # Límites de largo: maxlength (navegador) + validador (servidor).
        # El del navegador se puede saltar; el del servidor no.
        for nombre, limite in LIMITES_TEXTO.items():
            campo = self.fields[nombre]
            campo.widget.attrs["maxlength"] = limite
            campo.validators.append(MaxLengthValidator(limite))

        # El calendario no deja elegir fechas futuras (el modelo también
        # lo valida en el servidor con validar_fecha_nacimiento).
        if "fecha_nacimiento" in self.fields:
            minima, maxima = limites_fecha_nacimiento()
            self.fields["fecha_nacimiento"].widget.attrs["min"] = minima.isoformat()
            self.fields["fecha_nacimiento"].widget.attrs["max"] = maxima.isoformat()

        # Sin esto la lista muestra "---------" como primera opción.
        self.fields["especialidad"].empty_label = "Selecciona una especialidad"

        # Task 33: la lista solo debe mostrar especialidades activas.
        # Si una especialidad se desactiva (Especialidad.activa=False),
        # deja de aparecer como opción para nuevos pacientes, pero las
        # solicitudes que ya la usaban no se ven afectadas (la FK sigue
        # apuntando a la especialidad, solo que ya no se ofrece de nuevo).
        self.fields["especialidad"].queryset = Especialidad.objects.filter(activa=True)

        # Clases de Bootstrap para que el formulario se vea ordenado.
        for campo in self.fields.values():
            es_lista = isinstance(campo.widget, forms.Select)
            campo.widget.attrs["class"] = "form-select" if es_lista else "form-control"

    def clean_nombre_completo(self):
        return normalizar_nombre(self.cleaned_data["nombre_completo"])

    def clean_motivo_consulta(self):
        motivo = limpiar_texto(self.cleaned_data["motivo_consulta"])
        if len(motivo) < MOTIVO_LARGO_MINIMO:
            raise forms.ValidationError(
                f"Describe el motivo con al menos {MOTIVO_LARGO_MINIMO} caracteres."
            )
        return motivo

    def clean(self):
        cleaned = super().clean()
        # AB#83: un paciente no puede tener dos solicitudes activas (no
        # terminadas) para la misma especialidad.
        especialidad = cleaned.get("especialidad")
        if self.perfil is not None and especialidad is not None:
            activas = Solicitud.objects.filter(
                paciente=self.perfil.usuario, especialidad=especialidad
            ).exclude(estado=Solicitud.Estado.TERMINADO)
            if activas.exists():
                self.add_error(
                    "especialidad",
                    "Ya tienes una solicitud en curso para esta especialidad.",
                )
        # Limpieza de caracteres de control en el resto de los textos largos.
        for nombre in ("experiencia_previa", "antecedentes_personales", "antecedentes_familiares"):
            if nombre in cleaned and cleaned[nombre]:
                cleaned[nombre] = limpiar_texto(cleaned[nombre])
        return cleaned

    def clean_telefono(self):
        return normalizar_telefono(self.cleaned_data["telefono"])


# ============================================
# AB#82 (REQ-17): Formulario de registro del paciente
# ============================================
class RegistroPacienteForm(forms.ModelForm):
    correo = forms.EmailField(label="Correo electrónico", max_length=150)
    password1 = forms.CharField(
        label="Contraseña",
        help_text="De 10 a 50 caracteres, con mayúscula, minúscula, número y símbolo.",
        strip=False,
        max_length=PASSWORD_LARGO_MAXIMO,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    password2 = forms.CharField(
        label="Repite la contraseña",
        strip=False,
        max_length=PASSWORD_LARGO_MAXIMO,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    class Meta:
        model = PerfilPaciente
        fields = ["nombre_completo", "fecha_nacimiento", "rut", "telefono"]
        widgets = {
            "fecha_nacimiento": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "rut": forms.TextInput(attrs={"placeholder": "12.345.678-5"}),
            "telefono": forms.TextInput(attrs={"type": "tel", "placeholder": "+56 9 1234 5678"}),
        }

    field_order = [
        "nombre_completo", "correo", "fecha_nacimiento", "rut", "telefono",
        "password1", "password2",
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # El calendario solo deja elegir entre hace 120 años y hace 18 años.
        minima, maxima = limites_fecha_nacimiento(EDAD_MINIMA_REGISTRO)
        self.fields["fecha_nacimiento"].widget.attrs["min"] = minima.isoformat()
        self.fields["fecha_nacimiento"].widget.attrs["max"] = maxima.isoformat()
        self.fields["nombre_completo"].widget.attrs["maxlength"] = NOMBRE_LARGO_MAXIMO
        self.fields["telefono"].widget.attrs["maxlength"] = "16"
        for campo in self.fields.values():
            campo.widget.attrs["class"] = "form-control"

    def clean_fecha_nacimiento(self):
        fecha = self.cleaned_data["fecha_nacimiento"]
        validar_mayor_de_edad(fecha)
        return fecha

    def clean_nombre_completo(self):
        return normalizar_nombre(self.cleaned_data["nombre_completo"])

    def clean_telefono(self):
        return normalizar_telefono(self.cleaned_data["telefono"])

    def clean_correo(self):
        # Siempre en minúsculas, para detectar correos repetidos.
        return self.cleaned_data["correo"].strip().lower()

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get("password1"), cleaned.get("password2")
        if p1 and p2:
            if p1 != p2:
                self.add_error("password2", "Las contraseñas no coinciden.")
            else:
                # Mismos validadores de AUTH_PASSWORD_VALIDATORS (largo,
                # contraseñas comunes, solo números, parecido al correo/nombre).
                candidato = User(
                    username="",
                    email=cleaned.get("correo", ""),
                    first_name=cleaned.get("nombre_completo", ""),
                )
                try:
                    validate_password(p1, user=candidato)
                except forms.ValidationError as error:
                    self.add_error("password1", error)
        return cleaned
