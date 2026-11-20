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
from django.conf import settings
# ============================================
# Task 31: Proteger datos sensibles del formulario
# Issue padre: REQ-08 (Cifrado de datos sensibles)
# --------------------------------------------
# Importamos los campos cifrados de django-encrypted-model-fields.
# Por debajo usan Fernet (AES-128 + HMAC), que es lo que pide
# el contexto del proyecto (no AES-256 manual).
# ============================================
from encrypted_model_fields.fields import EncryptedCharField, EncryptedTextField
from .validators import (
    formatear_rut,
    validar_fecha_nacimiento,
    validar_rut,
)


class Solicitud(models.Model):
    """
    Solicitud de atención odontológica ingresada por un paciente.

    Guarda tanto los datos de contacto del paciente como sus
    antecedentes de salud. RUT y antecedentes son datos sensibles
    y están cifrados con django-encrypted-model-fields (REQ-08,
    Task 31). El cifrado se hace de forma transparente: al leer
    desde el ORM se ve el texto plano, pero en MySQL queda cifrado.
    """

    class Estado(models.TextChoices):
        # Ciclo de vida (REQ-18): PENDIENTE -> DERIVADA (el Coordinador
        # asigna estudiante y horario) -> REALIZADO (el estudiante atendió
        # al paciente) -> TERMINADO (ficha y reporte completos).
        PENDIENTE = "PENDIENTE", "Pendiente"
        DERIVADA = "DERIVADA", "Derivada"
        REALIZADO = "REALIZADO", "Realizado"
        TERMINADO = "TERMINADO", "Terminado"

    # Transiciones permitidas: no se pueden saltar etapas ni volver atrás.
    # Se valida en el servidor (nunca confiar en lo que mande el navegador).
    TRANSICIONES = {
        "PENDIENTE": {"DERIVADA"},
        "DERIVADA": {"REALIZADO"},
        "REALIZADO": {"TERMINADO"},
        "TERMINADO": set(),
    }

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
    rut = EncryptedCharField(
        "RUT",
        max_length=100,
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
    # Cambiados a EncryptedTextField. Fernet cifra el contenido
    # completo antes de guardarlo en MySQL.
    antecedentes_personales = EncryptedTextField(
        "antecedentes de salud personales",
        blank=True,
    )

    # Task 31: Proteger datos sensibles del formulario (REQ-08)
    antecedentes_familiares = EncryptedTextField(
        "antecedentes de salud familiares",
        blank=True,
    )

    # Task 50: Crear la página "mis pacientes" del estudiante
    # Issue padre: REQ-06 (Vista restringida del estudiante)
    # Es null mientras la solicitud está PENDIENTE. SET_NULL para que
    # borrar la cuenta de un estudiante no borre la solicitud del paciente.
    estudiante_asignado = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="solicitudes_asignadas",
        verbose_name="estudiante asignado",
    )

    # Auditoría de la derivación: estudiante asignado, responsable y fecha.
    derivado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="solicitudes_derivadas_por",
        verbose_name="derivado por",
    )
    fecha_derivacion = models.DateTimeField(
        "fecha de derivación",
        null=True,
        blank=True,
    )

    # Horario de la atención, definido por el Coordinador al derivar (REQ-18).
    fecha_atencion = models.DateTimeField(
        "fecha y hora de atención",
        null=True,
        blank=True,
    )

    # AB#83 (REQ-17): cuenta del paciente que hizo la reserva con sesión
    # iniciada. Es null cuando la solicitud se envió sin cuenta (formulario
    # público). SET_NULL: borrar la cuenta no borra la historia clínica.
    paciente = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="solicitudes_propias",
        verbose_name="paciente (cuenta)",
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

    def puede_pasar_a(self, nuevo_estado):
        """True si el cambio de estado respeta el ciclo de vida."""
        return nuevo_estado in self.TRANSICIONES.get(self.estado, set())

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


# ============================================
# AB#82 (REQ-17): Registro de pacientes con cuenta
# --------------------------------------------
# Datos del paciente que se registra. El User de Django guarda solo
# lo necesario para iniciar sesión (correo como usuario + contraseña
# con hash) y queda INACTIVO hasta que el Coordinador acepte el registro
# (AB#84). RUT es dato sensible: va cifrado (REQ-08).
# ============================================
class PerfilPaciente(models.Model):

    class Estado(models.TextChoices):
        PENDIENTE = "PENDIENTE", "Pendiente de revisión"
        ACEPTADO = "ACEPTADO", "Aceptado"
        RECHAZADO = "RECHAZADO", "Rechazado"

    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="perfil_paciente",
    )
    nombre_completo = models.CharField("nombre completo", max_length=150)
    fecha_nacimiento = models.DateField(
        "fecha de nacimiento", validators=[validar_fecha_nacimiento]
    )
    # Cifrado: no se puede filtrar ni exigir unicidad (igual que en Solicitud).
    rut = EncryptedCharField("RUT", max_length=100, validators=[validar_rut])
    telefono = models.CharField("teléfono", max_length=20)

    estado = models.CharField(
        "estado", max_length=10, choices=Estado.choices, default=Estado.PENDIENTE
    )
    fecha_registro = models.DateTimeField("fecha de registro", auto_now_add=True)

    # Los completa el Coordinador al revisar (AB#84).
    revisado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="registros_revisados",
    )
    fecha_revision = models.DateTimeField("fecha de revisión", null=True, blank=True)

    class Meta:
        verbose_name = "perfil de paciente"
        verbose_name_plural = "perfiles de pacientes"
        ordering = ["-fecha_registro"]
        indexes = [models.Index(fields=["estado", "fecha_registro"])]

    def __str__(self):
        # Sin nombre ni RUT: este texto puede aparecer en logs y en el admin.
        return f"Perfil de paciente #{self.pk} ({self.estado})"

    def save(self, *args, **kwargs):
        self.rut = formatear_rut(self.rut)
        super().save(*args, **kwargs)
