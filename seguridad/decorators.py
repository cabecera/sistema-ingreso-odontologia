from django.core.exceptions import PermissionDenied
from django.contrib.auth.decorators import login_required

def role_required(*allowed_roles):
    """
    Decorador que verifica si el usuario autenticado pertenece a uno de los roles (grupos) permitidos.
    """
    def decorator(view_func):
        @login_required
        def _wrapped_view(request, *args, **kwargs):
            # Si es superusuario, tiene acceso completo
            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)
            
            # Verificar si pertenece a alguno de los grupos asignados
            user_groups = request.user.groups.values_list('name', flat=True)
            if any(role in user_groups for role in allowed_roles):
                return view_func(request, *args, **kwargs)
            
            # Si no tiene el rol, deniega el acceso (Error 403)
            raise PermissionDenied
        return _wrapped_view
    return decorator