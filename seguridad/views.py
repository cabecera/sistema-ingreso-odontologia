# ============================================
# AB#83 (REQ-17): Inicio de sesión con destino según el rol
# --------------------------------------------
# Un solo login para todos. Si el usuario es Paciente, al entrar va a
# "Mis solicitudes"; el resto va al inicio como siempre. El parámetro
# ?next= sigue mandando si viene (Django valida que sea un destino seguro).
# Las cuentas pendientes o rechazadas están inactivas, así que el login
# estándar de Django las rechaza solo.
# ============================================
from django.contrib.auth.views import LoginView
from django.urls import reverse


class LoginPorRol(LoginView):
    template_name = "seguridad/login.html"

    def get_default_redirect_url(self):
        if self.request.user.groups.filter(name="Paciente").exists():
            return reverse("pacientes:mis_solicitudes")
        return super().get_default_redirect_url()
