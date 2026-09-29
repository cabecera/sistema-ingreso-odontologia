from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from seguridad.decorators import role_required

# Aplica el decorador segun las funciones que tengas definidas en este archivo.
# Por ejemplo, si tienes una vista de dashboard o panel de administracion:

@role_required('Administrador')
def panel_administracion(request):
    """
    Vista de administracion restringida exclusivamente para el rol Administrador.
    """
    return render(request, 'administracion/index.html')


