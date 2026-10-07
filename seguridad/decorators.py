# ============================================
# Follow-up Task 35 (Issue GitHub #16)
# Issue padre: REQ-07 (Control de acceso basado en roles)
# --------------------------------------------
# Decorador que restringe el acceso a una vista según el rol
# (Group de Django) del usuario autenticado.
#
# Ubicación: vive en seguridad/ porque es un mecanismo
# transversal de RBAC usado por los demás módulos
# (administracion, coordinacion, estudiantes), no lógica
# propia de ninguno de ellos — coincide con la arquitectura
# de la Wiki, que describe "seguridad" como la app encargada
# de autenticación, RBAC, cifrado y auditoría.
# ============================================

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def role_required(*allowed_roles):
    """
    Restringe el acceso a una vista según el rol (Group de Django)
    del usuario autenticado.

    Primero exige que el usuario esté autenticado (igual que
    @login_required): si no lo está, se le redirige a LOGIN_URL.
    Ya autenticado, permite el acceso sin restricción a los
    superusuarios. Para el resto, verifica que pertenezca a alguno
    de los grupos indicados en allowed_roles; si no pertenece a
    ninguno, se lanza PermissionDenied (Django responde con un
    error 403).

    Ejemplo de uso:

        @role_required('Coordinador')
        def listado_solicitudes(request):
            ...

        @role_required('Coordinador', 'Super Administrador')
        def derivar_solicitud(request):
            ...

    Casos cubiertos:
    - Usuario anónimo (no autenticado): login_required lo redirige
      a la página de inicio de sesión antes de llegar a la
      verificación de rol.
    - Usuario autenticado sin ningún grupo asignado: se le deniega
      el acceso con PermissionDenied (403), igual que si tuviera
      un rol no autorizado.
    - Usuario autenticado con el rol correcto: accede normalmente.
    - Superusuario: accede siempre, sin importar los grupos que
      se le exijan a la vista.
    """

    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            # Si es superusuario, tiene acceso completo.
            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)

            # Verificar si pertenece a alguno de los grupos permitidos.
            user_groups = request.user.groups.values_list("name", flat=True)
            if any(role in user_groups for role in allowed_roles):
                return view_func(request, *args, **kwargs)

            # No tiene el rol requerido: acceso denegado (403).
            raise PermissionDenied

        return _wrapped_view

    return decorator