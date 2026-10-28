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
@role_required('Super Administrador', 'Coordinador')
def listado_solicitudes(request):
    """
    Listado de todas las solicitudes de atencion, pensado para que
    el Coordinador decida a cual derivar primero.
    """
    pendientes = Solicitud.objects.filter(
        estado=Solicitud.Estado.PENDIENTE
    ).select_related("especialidad").order_by("fecha_creacion")

    derivadas = Solicitud.objects.filter(
        estado=Solicitud.Estado.DERIVADA
    ).select_related("especialidad", "estudiante_asignado")

    return render(
        request,
        "coordinacion/listado.html",
        {
            "pendientes": pendientes,
            "derivadas": derivadas,
        },
    )
