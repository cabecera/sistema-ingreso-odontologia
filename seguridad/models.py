from django.db import models
from django.conf import settings

class BitacoraAuditoria(models.Model):
    """
    Modelo para registrar automáticamente las acciones relevantes del sistema,
    como las derivaciones formales a estudiantes (Task 54).
    """
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        verbose_name="Usuario"
        
    )
    accion = models.CharField(max_length=255, verbose_name="Acción Realizada")
    detalles = models.TextField(blank=True, null=True, verbose_name="Detalles")
    fecha_hora = models.DateTimeField(auto_now_add=True, verbose_name="Fecha y Hora")

    class Meta:
        verbose_name = "Registro de Auditoría"
        verbose_name_plural = "Registros de Auditoría"
        ordering = ["-fecha_hora"]

    def __str__(self):
        return f"{self.fecha_hora.strftime('%Y-%m-%d %H:%M')} - {self.usuario} - {self.accion}"
    
    