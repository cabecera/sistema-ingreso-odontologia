# ============================================
# Task 59: Gestión de usuarios (REQ-14)
# --------------------------------------------
# Formulario para que el Super Administrador cree cuentas del personal.
# Hereda de UserCreationForm: la contraseña se escribe dos veces, pasa
# por los validadores de Django (largo, comunes, numéricas) y se guarda
# con hash, nunca en texto plano. El rol sale de una lista cerrada
# (whitelist): no se acepta ningún grupo que no esté en ROLES.
# ============================================

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import Group, User

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
