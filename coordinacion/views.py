from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.utils.dateparse import parse_date

from seguridad.decorators import role_required
from pacientes.models import Solicitud
from administracion.models import Especialidad

# Ejemplo para las vistas del modulo de coordinacion:

@role_required('Super Administrador', 'Coordinador')
def panel_coordinacion(request):
    """
    Vista de coordinacion accesible para SuperAdministradores y Coordinadores.
    """
    return render(request, 'coordinacion/dashboard.html')


# ============================================
# Tasks 47 y 49: Listado de solicitudes para el Coordinador
# Issue padre: REQ-04 (Listado y priorizacion de solicitudes)
# --------------------------------------------
# El decorador va puesto desde el principio (no se agrega
# despues como parche): la tarea 49 "restringir el listado
# solo al coordinador" queda resuelta aqui mismo, con el mismo
# patron que ya usa panel_coordinacion.
#
# Priorizacion: las solicitudes PENDIENTE se muestran primero
# (son las que requieren accion), ordenadas de la mas antigua
# a la mas reciente, para que el Coordinador atienda primero a
# quien lleva mas tiempo esperando. Las DERIVADA quedan despues,
# ordenadas de la mas reciente a la mas antigua (Meta.ordering
# del modelo), solo como referencia/historial.
# ============================================
@role_required('Super Administrator', 'Coordinador')
def listado_solicitudes(request):
    """
    Vista del listado de solicitudes con filtros de búsqueda (Task 48).
    Permite filtrar por especialidad, fecha o estado de forma segura.
    """
    # 1. Consulta base optimizada con select_related para evitar consultas lentas (N+1)
    solicitudes = Solicitud.objects.select_related("especialidad", "estudiante_asignado").all()

    # 2. Capturar los parámetros enviados por el formulario (método GET)
    especialidad_filtro = request.GET.get('especialidad', '')
    fecha_filtro = request.GET.get('fecha', '')
    estado_filtro = request.GET.get('estado', '')

    # 3. Aplicar filtros condicionales de forma segura
    if especialidad_filtro:
        solicitudes = solicitudes.filter(especialidad__nombre=especialidad_filtro)

    if fecha_filtro:
        try:
            fecha_valida = parse_date(fecha_filtro)
            if fecha_valida:
                solicitudes = solicitudes.filter(fecha_creacion__date=fecha_valida)
            else:
                solicitudes = Solicitud.objects.none() # Retorna vacío si el formato de fecha es incorrecto
        except (ValidationError, ValueError):
            solicitudes = Solicitud.objects.none() # Previene el Error 500 si ingresan texto inválido

    if estado_filtro:
        solicitudes = solicitudes.filter(estado=estado_filtro)

    # 4. Obtener las especialidades activas desde la BD para el menú desplegable dinámico
    especialidades_list = Especialidad.objects.filter(activa=True)

    # 5. Contexto para la plantilla HTML
    context = {
        "solicitudes": solicitudes,
        "especialidades": especialidades_list,
        "especialidad_filtro": especialidad_filtro,
        "fecha_filtro": fecha_filtro,
        "estado_filtro": estado_filtro,
    }
    
    return render(request, "coordinacion/listado.html", context)