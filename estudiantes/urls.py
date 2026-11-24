# ============================================
# Task 44: Bloquear el acceso a quien no haya iniciado sesión
# Issue padre: REQ-03 (Autenticación segura de personal interno)
# ============================================
from django.urls import path

from . import views

app_name = "estudiantes"

urlpatterns = [
    path("", views.panel_estudiantes, name="panel"),
    ##TASK 50: Crear la página "mis pacientes" del estudiante
    path("mis-pacientes/", views.mis_pacientes, name="mis_pacientes"),
    # Task 86: el estudiante marca la atención como realizada
    path("pacientes/<int:pk>/realizada/", views.marcar_realizada, name="marcar_realizada"),
    # Ficha que llenó el paciente al reservar (solo lectura)
    path("pacientes/<int:pk>/solicitud/", views.ver_solicitud, name="ver_solicitud"),
    # AB#87: ficha clínica y reporte
    path("pacientes/<int:pk>/ficha/", views.completar_ficha, name="completar_ficha"),
    path("pacientes/<int:pk>/reporte/", views.ver_reporte, name="ver_reporte"),
]
