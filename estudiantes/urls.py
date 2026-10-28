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
]
