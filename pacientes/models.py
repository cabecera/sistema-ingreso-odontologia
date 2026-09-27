from django.db import models

from .validators import (
    formatear_rut,
    validar_fecha_nacimiento,
    validar_rut,
)


class Solicitud(models.Model):
    """Solicitud de atención enviada por un paciente (REQ-01).

    Los datos son públicos de ingreso (el paciente no tiene cuenta), pero
    RUT y antecedentes de salud son datos sensibles: en la tarea #31 se
    cambian a campos cifrados (REQ-08). Ver los comentarios "CIFRAR".
    """

    class Estado(models.TextChoices):
        PENDIENTE = "PENDIENTE", "Pendiente"
        DERIVADA = "DERIVADA", "Derivada"

    # --- Datos personales ---
    nombre_completo = models.CharField("nombre completo", max_length=150)
    fecha_nacimiento = models.DateField(
        "fecha de nacimiento",
        validators=[validar_fecha_nacimiento],
    )
    # CIFRAR (tarea #31): cambiar a EncryptedCharField. Un campo cifrado no
    # se puede filtrar ni buscar con el ORM, por eso no lleva unique=True.
    rut = models.CharField("RUT", max_length=12, validators=[validar_rut])
    telefono = models.CharField("teléfono", max_length=20)

    # --- Datos de la solicitud ---
    motivo_consulta = models.TextField("motivo de consulta")
    # Ajustar "administracion.Especialidad" si el catálogo (tarea #32) queda
    # en otra app. PROTECT evita borrar una especialidad que ya tiene solicitudes.
    especialidad = models.ForeignKey(
        "administracion.Especialidad",
        on_delete=models.PROTECT,
        related_name="solicitudes",
        verbose_name="especialidad",
    )
    experiencia_previa = models.TextField(
        "experiencia previa",
        blank=True,
        help_text="Tratamientos o atenciones anteriores relacionados con la solicitud.",
    )

    # --- Antecedentes de salud ---
    # CIFRAR (tarea #31): cambiar a EncryptedTextField.
    antecedentes_personales = models.TextField(
        "antecedentes de salud personales", blank=True
    )
    # CIFRAR (tarea #31): cambiar a EncryptedTextField.
    antecedentes_familiares = models.TextField(
        "antecedentes de salud familiares", blank=True
    )

    # --- Gestión ---
    estado = models.CharField(
        "estado",
        max_length=10,
        choices=Estado.choices,
        default=Estado.PENDIENTE,
    )
    fecha_creacion = models.DateTimeField("fecha de creación", auto_now_add=True)

    class Meta:
        verbose_name = "solicitud"
        verbose_name_plural = "solicitudes"
        ordering = ["-fecha_creacion"]
        indexes = [
            models.Index(fields=["estado", "fecha_creacion"]),
            models.Index(fields=["especialidad", "estado"]),
        ]

    def __str__(self):
        # No incluye nombre ni RUT: este texto aparece en el admin y en logs.
        return f"Solicitud #{self.pk} ({self.especialidad})"

    def save(self, *args, **kwargs):
        # Guarda el RUT siempre con el mismo formato (12345678-5).
        self.rut = formatear_rut(self.rut)
        super().save(*args, **kwargs)
