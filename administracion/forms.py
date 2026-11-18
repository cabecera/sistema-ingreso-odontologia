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

from administracion.models import Especialidad

ROLES = ("Coordinador", "Estudiante", "Super Administrador")


class UsuarioNuevoForm(UserCreationForm):
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


class EspecialidadForm(forms.ModelForm):
    class Meta:
        model = Especialidad
        fields = ("nombre", "descripcion", "activa")
        widgets = {
            "nombre": forms.TextInput(attrs={"class": "form-control"}),
            "descripcion": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
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
        return " ".join(self.cleaned_data.get("descripcion", "").split())
