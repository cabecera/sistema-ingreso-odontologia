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
from datetime import date

from django import forms
from django.core.validators import MaxLengthValidator

from administracion.models import Especialidad

from .models import Solicitud

LIMITES_TEXTO = {
    "motivo_consulta": 500,
    "experiencia_previa": 500,
    "antecedentes_personales": 1000,
    "antecedentes_familiares": 1000,
}


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
            "telefono": forms.TextInput(attrs={"type": "tel", "placeholder": "+56 9 1234 5678"}),
            "motivo_consulta": forms.Textarea(attrs={"rows": 3}),
            "experiencia_previa": forms.Textarea(attrs={"rows": 3}),
            "antecedentes_personales": forms.Textarea(attrs={"rows": 4}),
            "antecedentes_familiares": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Límites de largo: maxlength (navegador) + validador (servidor).
        # El del navegador se puede saltar; el del servidor no.
        for nombre, limite in LIMITES_TEXTO.items():
            campo = self.fields[nombre]
            campo.widget.attrs["maxlength"] = limite
            campo.validators.append(MaxLengthValidator(limite))

        # El calendario no deja elegir fechas futuras (el modelo también
        # lo valida en el servidor con validar_fecha_nacimiento).
        self.fields["fecha_nacimiento"].widget.attrs["max"] = date.today().isoformat()

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

    def clean_telefono(self):
        # Acepta formatos como "+56 9 1234 5678" o "(2) 2345-6789",
        # pero rechaza letras y símbolos raros.
        telefono = self.cleaned_data["telefono"].strip()
        if not re.fullmatch(r"\+?[0-9 ()-]+", telefono):
            raise forms.ValidationError(
                "Usa solo números, espacios, guiones, paréntesis y un + inicial."
            )
        if not 8 <= len(re.sub(r"\D", "", telefono)) <= 15:
            raise forms.ValidationError("El teléfono debe tener entre 8 y 15 dígitos.")
        return telefono
