# ============================================
# AB#83 (REQ-17): Inicio de sesión con destino según el rol
# --------------------------------------------
# Un solo login para todos. Cada rol aterriza en su página principal:
#   Super Administrador / superusuario -> panel de administración
#   Coordinador                        -> panel de coordinación
#   Estudiante                         -> panel del estudiante
#   Paciente                           -> mis solicitudes
# El parámetro ?next= sigue mandando si viene (Django valida que sea un
# destino seguro). Las cuentas pendientes o rechazadas están inactivas,
# así que el login estándar de Django las rechaza solo.
# ============================================
from django.contrib.auth.views import LoginView

from .forms import PERSONAL, LoginForm
from .inicio import pagina_inicio


class LoginPorRol(LoginView):
    template_name = "seguridad/login.html"
    authentication_form = LoginForm

    def get_initial(self):
        # ?tipo=personal muestra el ingreso con usuario; por defecto, con RUT.
        tipo = PERSONAL if self.request.GET.get("tipo") == PERSONAL else "paciente"
        return {"tipo": tipo}

    def get_default_redirect_url(self):
        return pagina_inicio(self.request.user) or super().get_default_redirect_url()
