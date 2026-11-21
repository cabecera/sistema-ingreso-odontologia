# ============================================
# AB#83 (REQ-17): Inicio de sesión con destino según el rol
# --------------------------------------------
# Un solo login para todos. Cada rol aterriza en su página principal:
#   Super Administrador / superusuario -> panel de administración
#   Coordinador                        -> panel de coordinación
#   Estudiante                         -> mis pacientes
#   Paciente                           -> mis solicitudes
# El parámetro ?next= sigue mandando si viene (Django valida que sea un
# destino seguro). Las cuentas pendientes o rechazadas están inactivas,
# así que el login estándar de Django las rechaza solo.
# ============================================
from django.contrib.auth.views import LoginView
from django.urls import reverse


class LoginPorRol(LoginView):
    template_name = "seguridad/login.html"

    def get_default_redirect_url(self):
        usuario = self.request.user
        roles = set(usuario.groups.values_list("name", flat=True))
        if usuario.is_superuser or "Super Administrador" in roles:
            return reverse("administracion:panel")
        if "Coordinador" in roles:
            return reverse("coordinacion:panel")
        if "Estudiante" in roles:
            return reverse("estudiantes:mis_pacientes")
        if "Paciente" in roles:
            return reverse("pacientes:mis_solicitudes")
        return super().get_default_redirect_url()
