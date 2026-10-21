from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from seguridad.decorators import role_required

#Arreglar
@role_required('Super Administrador')
def panel_administracion(request):
    """
    Vista de administracion restringida exclusivamente para el rol Super Administrador.
    """
    return render(request, 'administracion/index.html')