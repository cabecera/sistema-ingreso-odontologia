# ============================================
# Task 44: Bloquear el acceso a quien no haya iniciado sesión
# Issue padre: REQ-03 (Autenticación segura de personal interno)
# ============================================
from django.urls import path

from . import views

app_name = "coordinacion"

urlpatterns = [
    path("", views.panel_coordinacion, name="panel"),
    # ============================================
    # Tasks 47/49: Listado de solicitudes (REQ-04)
    # ============================================
    path('listado/', views.listado_solicitudes, name='listado_solicitudes'),
    path('estudiantes/', views.lista_estudiantes, name='lista_estudiantes'),
    # AB#84: revisión de registros de pacientes (REQ-17)
    path('registros/', views.lista_registros, name='lista_registros'),
    path('registros/<int:pk>/aceptar/', views.aceptar_registro, name='aceptar_registro'),
    path('registros/<int:pk>/rechazar/', views.rechazar_registro, name='rechazar_registro'),
    # AB#87: reporte de una atención terminada (solo lectura)
    path('solicitudes/<int:pk>/reporte/', views.reporte_solicitud, name='reporte_solicitud'),
    path('derivar/<int:pk>/', views.derivar_solicitud, name='derivar_solicitud'),
]
