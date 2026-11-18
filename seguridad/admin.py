from django.contrib import admin

from .models import BitacoraAuditoria


@admin.register(BitacoraAuditoria)
class BitacoraAuditoriaAdmin(admin.ModelAdmin):
    """Bitácora de solo lectura: la evidencia no se agrega, edita ni borra."""

    list_display = ("fecha_hora", "usuario", "accion")
    list_filter = ("accion",)
    readonly_fields = ("usuario", "accion", "detalles", "fecha_hora")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
