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
    # Task 59: gestión de usuarios
    path("usuarios/", views.lista_usuarios, name="usuarios"),
    path("usuarios/nuevo/", views.usuario_nuevo, name="usuario_nuevo"),
    path(
        "usuarios/<int:pk>/estado/",
        views.usuario_cambiar_estado,
        name="usuario_cambiar_estado",
    ),
    # Task 60: gestión de especialidades
    path("especialidades/", views.lista_especialidades, name="especialidades"),
    path("especialidades/nueva/", views.especialidad_nueva, name="especialidad_nueva"),
    path(
        "especialidades/<int:pk>/editar/",
        views.especialidad_editar,
        name="especialidad_editar",
    ),
    path(
        "especialidades/<int:pk>/estado/",
        views.especialidad_cambiar_estado,
        name="especialidad_cambiar_estado",
    ),
]
