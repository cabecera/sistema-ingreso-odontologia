from django.db import models

# Create your models here.
# ============================================
# Task 32: Crear catálogo de especialidades
# Issue padre: REQ-02 (Selección de especialidad)
# --------------------------------------------
# Modelo que representa las especialidades
# odontológicas disponibles en el sistema.
# Se usa en el formulario público (REQ-01) para
# que el paciente elija una al solicitar atención.
#
# Task relacionada: #29 (Solicitud) depende de este
# modelo por la ForeignKey "especialidad".
# ============================================


from django.db import models


class Especialidad(models.Model):
    """
    Catálogo de especialidades odontológicas.

    Ejemplos: Ortodoncia, Endodoncia, Periodoncia,
    Odontopediatría, Cirugía maxilofacial, etc.
    """

    # --- Datos de la especialidad ---
    # "nombre" es único para evitar duplicados en el catálogo.
    nombre = models.CharField(
        "nombre",
        max_length=100,
        unique=True,
    )

    # Descripción opcional (puede quedar vacía).
    descripcion = models.TextField(
        "descripción",
        blank=True,
    )

    # Bandera para desactivar sin borrar.
    # Si se desactiva, no debería aparecer en el formulario
    # público del paciente, pero se conserva por historial.
    activa = models.BooleanField(
        "activa",
        default=True,
        help_text="Si se desactiva, no aparece en el formulario público.",
    )

    class Meta:
        # Nombre en singular/plural para el admin de Django.
        verbose_name = "especialidad"
        verbose_name_plural = "especialidades"

        # Orden alfabético por defecto en cualquier consulta.
        ordering = ["nombre"]

    def __str__(self):
        # Representación legible en el admin y en logs.
        return self.nombre