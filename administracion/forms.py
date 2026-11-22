# ============================================
# Task 59: Gestión de usuarios (REQ-14)
# --------------------------------------------
# Formulario para que el Super Administrador cree cuentas del personal.
# Hereda de UserCreationForm: la contraseña se escribe dos veces, pasa
# por los validadores de Django (largo, comunes, numéricas) y se guarda
# con hash, nunca en texto plano. El rol sale de una lista cerrada
# (whitelist): no se acepta ningún grupo que no esté en ROLES.
# ============================================

import re

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import Group, User

from django.core.validators import MaxLengthValidator

from administracion.models import Especialidad
from pacientes.forms import (
    PASSWORD_LARGO_MAXIMO,
    limpiar_texto,
    normalizar_nombre,
)

# Usuario del personal: corto y sin símbolos. Empieza con letra, así nunca
# se confunde con un RUT (los pacientes ingresan con RUT, no con usuario).
PATRON_USUARIO = re.compile(r"^[a-z][a-z0-9_]{3,19}$")
ROLES = ("Coordinador", "Estudiante", "Super Administrador")


class UsuarioNuevoForm(UserCreationForm):
    # Mismas reglas que el registro del paciente: nombres solo con letras,
    # espacios y guion; correo con formato válido, máximo 150 y único.
    first_name = forms.CharField(label="Nombre", max_length=50)
    last_name = forms.CharField(label="Apellido", max_length=50)
    email = forms.EmailField(label="Correo electrónico", max_length=150)
    rol = forms.ChoiceField(
        label="Rol",
        choices=[("", "Elegir rol…")] + [(r, r) for r in ROLES],
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "first_name", "last_name", "email")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for nombre, campo in self.fields.items():
            clase = "form-select" if nombre == "rol" else "form-control"
            campo.widget.attrs["class"] = clase
        self.fields["username"].help_text = (
            "4 a 20 caracteres: minúsculas, números y guion bajo; empieza con letra."
        )
        # Contraseña: máximo 50 (el resto de la política está en AUTH_PASSWORD_VALIDATORS).
        for nombre in ("password1", "password2"):
            self.fields[nombre].widget.attrs["maxlength"] = PASSWORD_LARGO_MAXIMO
            self.fields[nombre].validators.append(MaxLengthValidator(PASSWORD_LARGO_MAXIMO))

    def clean_first_name(self):
        return normalizar_nombre(self.cleaned_data["first_name"], minimo=2, maximo=50)

    def clean_last_name(self):
        return normalizar_nombre(self.cleaned_data["last_name"], minimo=2, maximo=50)

    def clean_email(self):
        correo = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=correo).exists():
            raise forms.ValidationError("Ya existe una cuenta con ese correo.")
        return correo

    def clean_username(self):
        username = super().clean_username()
        if username is None:  # ya hay un error (usuario repetido)
            return username
        if not PATRON_USUARIO.match(username):
            raise forms.ValidationError(
                "Entre 4 y 20 caracteres: minúsculas, números y guion bajo; debe empezar con una letra."
            )
        return username

    def save(self, commit=True):
        usuario = super().save(commit=False)
        # Nunca se crea personal con acceso al sitio de administración
        # de Django: is_staff e is_superuser quedan en False.
        usuario.is_staff = False
        usuario.is_superuser = False
        if commit:
            usuario.save()
            grupo, _ = Group.objects.get_or_create(name=self.cleaned_data["rol"])
            usuario.groups.add(grupo)
        return usuario


# ============================================
# Task 60: Gestión de especialidades (REQ-14)
# --------------------------------------------
# El nombre se normaliza (espacios) y no puede repetirse sin importar
# mayúsculas, porque el catálogo alimenta el formulario público.
# Solo se permiten letras, espacios y guion/punto/paréntesis: nada de
# símbolos que luego se muestren en listas o filtros.
# ============================================
PATRON_NOMBRE_ESPECIALIDAD = re.compile(r"^[^\W\d_][\w .()\-áéíóúüñÁÉÍÓÚÜÑ]*$", re.UNICODE)


DESCRIPCION_MAXIMO = 500


class EspecialidadForm(forms.ModelForm):
    class Meta:
        model = Especialidad
        fields = ("nombre", "descripcion", "activa")
        widgets = {
            "nombre": forms.TextInput(attrs={"class": "form-control"}),
            "descripcion": forms.Textarea(
                attrs={"class": "form-control", "rows": 3, "maxlength": DESCRIPCION_MAXIMO}
            ),
            "activa": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def clean_nombre(self):
        nombre = " ".join(self.cleaned_data["nombre"].split())
        if len(nombre) < 3:
            raise forms.ValidationError("El nombre debe tener al menos 3 caracteres.")
        if not PATRON_NOMBRE_ESPECIALIDAD.match(nombre) or "_" in nombre:
            raise forms.ValidationError(
                "Usa solo letras, espacios, punto, guion y paréntesis; no puede empezar con un número."
            )
        repetidas = Especialidad.objects.filter(nombre__iexact=nombre)
        if self.instance.pk:
            repetidas = repetidas.exclude(pk=self.instance.pk)
        if repetidas.exists():
            raise forms.ValidationError("Ya existe una especialidad con ese nombre.")
        return nombre

    def clean_descripcion(self):
        texto = " ".join(limpiar_texto(self.cleaned_data.get("descripcion", "")).split())
        if len(texto) > DESCRIPCION_MAXIMO:
            raise forms.ValidationError(f"No puede tener más de {DESCRIPCION_MAXIMO} caracteres.")
        return texto
