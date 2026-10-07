# ============================================
# Task 44: Bloquear el acceso a quien no haya iniciado sesión
# Issue padre: REQ-03 (Autenticación segura de personal interno)
# --------------------------------------------
# Conecta la vista de ejemplo panel_administracion (ya protegida
# con @role_required en views.py, Task 35) a una URL real, para
# poder probar de punta a punta que la protección funciona:
# sin login, con login pero sin el rol correcto, y con el rol
# correcto.
# ============================================
from django.urls import path

from . import views

app_name = "administracion"

urlpatterns = [
    path("", views.panel_administracion, name="panel"),
]
