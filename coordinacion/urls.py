# ============================================
# Task 44: Bloquear el acceso a quien no haya iniciado sesión
# Issue padre: REQ-03 (Autenticación segura de personal interno)
# ============================================
from django.urls import path

from . import views

app_name = "coordinacion"

urlpatterns = [
    path("", views.panel_coordinacion, name="panel"),
]
