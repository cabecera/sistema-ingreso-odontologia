from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from seguridad.decorators import role_required
from pacientes.models import Solicitud

# Ejemplo para las vistas del modulo de coordinacion:

@role_required('Super Administrador', 'Coordinador')
def panel_coordinacion(request):
    """
    Vista de coordinacion accesible para SuperAdministradores y Coordinadores.
    """
    return render(request, 'coordinacion/dashboard.html')

@role_required('Super Administrador', 'Coordinador')
def listado_solicitudes(request):
    """
    Vista del listado de solicitudes con filtros de búsqueda (Task 48).
    Permite filtrar por especialidad, fecha o estado.
    """
    # 1. Obtener todas las solicitudes base
    solicitudes = Solicitud.objects.all()

    # 2. Capturar los parámetros enviados por el formulario (método GET)
    especialidad = request.GET.get('especialidad', '')
    fecha = request.GET.get('fecha', '')
    estado = request.GET.get('estado', '')

    # 3. Aplicar filtros condicionales
    # 3. Aplicar filtros condicionales
    if especialidad:
        solicitudes = solicitudes.filter(especialidad__nombre=especialidad)
    if fecha:
        solicitudes = solicitudes.filter(fecha_creacion__date=fecha)
    if estado:
        solicitudes = solicitudes.filter(estado=estado)

    # 4. Contexto para la plantilla HTML
    context = {
        'solicitudes': solicitudes,
        'especialidad_filtro': especialidad,
        'fecha_filtro': fecha,
        'estado_filtro': estado,
    }
    
    return render(request, 'coordinacion/listado_solicitudes.html', context)


