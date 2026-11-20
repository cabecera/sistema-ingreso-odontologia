# ============================================
# AB#87 (REQ-18): Formulario de la ficha clínica
# --------------------------------------------
# Solo cuatro campos. La solicitud y el estudiante los pone el servidor
# (nunca vienen del navegador). Los textos tienen largo máximo y mínimo,
# se les quitan caracteres de control y la especialidad debe estar activa.
# ============================================
from django import forms
from django.core.validators import MaxLengthValidator

from administracion.models import Especialidad
from pacientes.forms import limpiar_texto
from pacientes.models import FichaClinica

LIMITE_TEXTO = 2000
MINIMO_EXAMEN = 20
MINIMO_REPORTE = 20


class FichaClinicaForm(forms.ModelForm):
    class Meta:
        model = FichaClinica
        # El orden es parte de la regla: primero el examen previo y
        # después la decisión de especialidad.
        fields = ["examen_previo", "observaciones", "especialidad_requerida", "reporte"]
        widgets = {
            "examen_previo": forms.Textarea(attrs={"rows": 5}),
            "observaciones": forms.Textarea(attrs={"rows": 3}),
            "reporte": forms.Textarea(attrs={"rows": 5}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for nombre in ("examen_previo", "observaciones", "reporte"):
            campo = self.fields[nombre]
            campo.widget.attrs["maxlength"] = LIMITE_TEXTO
            campo.validators.append(MaxLengthValidator(LIMITE_TEXTO))
        self.fields["especialidad_requerida"].queryset = Especialidad.objects.filter(activa=True)
        self.fields["especialidad_requerida"].empty_label = "Selecciona una especialidad"
        for campo in self.fields.values():
            es_lista = isinstance(campo.widget, forms.Select)
            campo.widget.attrs["class"] = "form-select" if es_lista else "form-control"

    def _texto_minimo(self, nombre, minimo, etiqueta):
        texto = limpiar_texto(self.cleaned_data[nombre])
        if len(texto) < minimo:
            raise forms.ValidationError(
                f"{etiqueta} debe tener al menos {minimo} caracteres."
            )
        return texto

    def clean_examen_previo(self):
        return self._texto_minimo("examen_previo", MINIMO_EXAMEN, "El examen previo")

    def clean_reporte(self):
        return self._texto_minimo("reporte", MINIMO_REPORTE, "El reporte")

    def clean_observaciones(self):
        return limpiar_texto(self.cleaned_data["observaciones"])
