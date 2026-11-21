# ============================================
# Task 42: Configurar el sistema de inicio de sesión
# Issue padre: REQ-03 (Autenticación segura de personal interno)
# --------------------------------------------
# Usa las vistas de login/logout que Django ya trae
# construidas (django.contrib.auth.views), en vez de
# escribirlas a mano. El nombre "login" coincide con
# LOGIN_URL que Paulina ya dejó en settings.py (Task 35).
# ============================================

from django.contrib.auth import views as auth_views
from django.urls import path

from .views import LoginPorRol

app_name = "seguridad"

urlpatterns = [
    path(
        "login/",
        LoginPorRol.as_view(),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
]