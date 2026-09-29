from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from seguridad.decorators import role_required

# Ejemplo para las vistas del modulo de coordinacion:

@role_required('Administrador', 'Coordinador')
def panel_coordinacion(request):
    """
    Vista de coordinacion accesible para Administradores y Coordinadores.
    """
    return render(request, 'coordinacion/dashboard.html')


