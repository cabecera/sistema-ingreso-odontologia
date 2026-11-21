from django.contrib import admin

from .models import Solicitud


@admin.register(Solicitud)
class SolicitudAdmin(admin.ModelAdmin):
    """Solo para limpiar datos de prueba (por ejemplo, solicitudes cifradas con
    una clave anterior). Mínimo privilegio: no se puede crear ni editar, y no se
    muestra ningún dato personal ni clínico (nombre, RUT, antecedentes); el
    detalle de la solicitud se ve solo en los paneles por rol."""

    list_display = ("id", "estado", "especialidad", "fecha_creacion")
    list_filter = ("estado", "especialidad")
    fields = ("estado", "especialidad", "fecha_creacion")
    readonly_fields = fields

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
