# ============================================
# Task 29: Crear modelo de Solicitud y su tabla
# Issue padre: REQ-01 (Registro público de solicitud)
# --------------------------------------------
# Modelo que representa la solicitud de atención que
# completa un paciente. El paciente NO tiene cuenta
# (REQ-01 dice "sin necesidad de cuenta"), así que este
# modelo es el único registro de esa persona en el sistema.
#
# Tareas relacionadas:
#   - #30 (Carlos): formulario público que crea estos registros.
#   - #31 (Carlos): cifrado de los campos sensibles (ver "CIFRAR").
#   - #32 (Carlos): catálogo de Especialidad, usado como ForeignKey.
#   - #33 (Guido): selector de especialidad en el formulario.
# ============================================

from django.db import models

from .validators import (
    formatear_rut,
    validar_fecha_nacimiento,
    validar_rut,
)


class Solicitud(models.Model):
    """
    Solicitud de atención odontológica ingresada por un paciente.

    Guarda tanto los datos de contacto del paciente como sus
    antecedentes de salud. RUT y antecedentes son datos sensibles:
    por ahora quedan como texto plano, y la tarea #31 los cambia a
    campos cifrados (EncryptedCharField / EncryptedTextField) para
    cumplir REQ-08. Los campos que hay que cambiar están marcados
    con el comentario "CIFRAR" para que no se nos olvide ninguno.
    """

    class Estado(models.TextChoices):
        # Solo dos estados por ahora: la solicitud llega como
        # PENDIENTE y pasa a DERIVADA cuando el Coordinador la
        # asigna a un estudiante (tarea de derivación, REQ-05).
        PENDIENTE = "PENDIENTE", "Pendiente"
        DERIVADA = "DERIVADA", "Derivada"

    # --- Datos personales del paciente ---
    nombre_completo = models.CharField("nombre completo", max_length=150)

    fecha_nacimiento = models.DateField(
        "fecha de nacimiento",
        # Valida que no sea una fecha futura ni absurdamente antigua
        # (ver pacientes/validators.py).
        validators=[validar_fecha_nacimiento],
    )

    # CIFRAR (tarea #31): cambiar a EncryptedCharField.
    # No lleva unique=True a propósito: un campo cifrado no se puede
    # comparar ni buscar con el ORM, así que la unicidad del RUT no
    # se puede garantizar a nivel de base de datos una vez cifrado.
    rut = models.CharField(
        "RUT",
        max_length=12,
        validators=[validar_rut],
        help_text="Se guarda siempre formateado como 12345678-5.",
    )

    telefono = models.CharField("teléfono", max_length=20)

    # --- Datos propios de la solicitud (REQ-01, REQ-02) ---
    motivo_consulta = models.TextField("motivo de consulta")

    # Referencia al catálogo de la tarea #32. Si Carlos cambia el
    # nombre de la app o del modelo, esta línea es la única que hay
    # que actualizar. on_delete=PROTECT porque no queremos que se
    # pueda borrar una especialidad que ya tiene solicitudes asociadas
    # (se perdería el historial de atenciones).
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

    # --- Antecedentes de salud (dato sensible, REQ-08) ---
    # CIFRAR (tarea #31): cambiar a EncryptedTextField.
    antecedentes_personales = models.TextField(
        "antecedentes de salud personales",
        blank=True,
    )

    # CIFRAR (tarea #31): cambiar a EncryptedTextField.
    antecedentes_familiares = models.TextField(
        "antecedentes de salud familiares",
        blank=True,
    )

    # --- Campos de gestión, para el panel del Coordinador (REQ-04) ---
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
        # Las más recientes primero: así el Coordinador ve de inmediato
        # lo último que llegó al abrir su panel.
        ordering = ["-fecha_creacion"]
        indexes = [
            # Acelera el filtro por estado y fecha que pide REQ-04.
            models.Index(fields=["estado", "fecha_creacion"]),
            # Acelera el filtro por especialidad + estado (REQ-04).
            models.Index(fields=["especialidad", "estado"]),
        ]

    def __str__(self):
        # A propósito NO incluye nombre ni RUT: este texto aparece en
        # el admin de Django y en cualquier log del sistema, y esos
        # lugares no deberían mostrar datos personales sin necesidad.
        return f"Solicitud #{self.pk} ({self.especialidad})"

    def save(self, *args, **kwargs):
        # Normaliza el RUT antes de guardar, para que en la base
        # siempre quede en el mismo formato (12345678-5), sin
        # importar cómo lo haya escrito el paciente en el formulario
        # (con puntos, sin puntos, con o sin guion).
        self.rut = formatear_rut(self.rut)
        super().save(*args, **kwargs)
