from datetime import date, datetime, time, timedelta

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone

from administracion.models import Especialidad
from pacientes.models import Solicitud
from seguridad.decorators import role_required
from seguridad.models import BitacoraAuditoria

# Ejemplo para las vistas del modulo de coordinacion:

@role_required('Super Administrador', 'Coordinador')
def panel_coordinacion(request):
    """
    Vista de coordinacion accesible para SuperAdministradores y Coordinadores.
    """
    return render(request, 'coordinacion/dashboard.html')


def _rango_del_dia(fecha):
    """Inicio y fin (excluyente) del día en la zona horaria del sitio.

    Se filtra por rango y no con __date porque en MySQL ese lookup usa
    CONVERT_TZ, que devuelve NULL si el servidor no tiene cargadas las
    tablas de zonas horarias (no se puede asegurar en un MySQL gestionado).
    """
    inicio = timezone.make_aware(datetime.combine(fecha, time.min))
    fin = timezone.make_aware(datetime.combine(fecha + timedelta(days=1), time.min))
    return inicio, fin


@role_required('Super Administrador', 'Coordinador')
def listado_solicitudes(request):
    """
    Listado de todas las solicitudes de atencion, pensado para que
    el Coordinador decida a cual derivar primero. Admite filtros por
    especialidad, fecha de ingreso y estado (Task 48).
    """
    especialidades = list(Especialidad.objects.all())
    ids_validos = {str(e.pk) for e in especialidades}

    especialidad_filtro = request.GET.get("especialidad", "").strip()
    fecha_texto = request.GET.get("fecha", "").strip()
    estado_filtro = request.GET.get("estado", "").strip()

    solicitudes = Solicitud.objects.select_related(
        "especialidad", "estudiante_asignado"
    )

    # Se ignora todo valor que no esté en el catálogo / no sea válido.
    if especialidad_filtro in ids_validos:
        solicitudes = solicitudes.filter(especialidad_id=int(especialidad_filtro))
    else:
        especialidad_filtro = ""

    fecha_filtro = ""
    fecha_invalida = False
    if fecha_texto:
        try:
            fecha = date.fromisoformat(fecha_texto)
            inicio, fin = _rango_del_dia(fecha)
        except (ValueError, OverflowError):
            fecha_invalida = True
        else:
            solicitudes = solicitudes.filter(
                fecha_creacion__gte=inicio, fecha_creacion__lt=fin
            )
            fecha_filtro = fecha.isoformat()

    if estado_filtro in Solicitud.Estado.values:
        solicitudes = solicitudes.filter(estado=estado_filtro)
    else:
        estado_filtro = ""

    pendientes = solicitudes.filter(
        estado=Solicitud.Estado.PENDIENTE
    ).order_by("fecha_creacion", "pk")
    derivadas = solicitudes.filter(estado=Solicitud.Estado.DERIVADA)

    return render(
        request,
        "coordinacion/listado.html",
        {
            "pendientes": pendientes,
            "derivadas": derivadas,
            "especialidades": especialidades,
            "estados": Solicitud.Estado.choices,
            "especialidad_filtro": especialidad_filtro,
            "fecha_filtro": fecha_filtro,
            "estado_filtro": estado_filtro,
            "fecha_invalida": fecha_invalida,
            "hay_filtros": bool(
                especialidad_filtro or fecha_filtro or estado_filtro
            ),
        },
    )


# ============================================
# Task 54: Derivación formal y registro automático de auditoría
# ============================================
@role_required('Super Administrador', 'Coordinador')
def derivar_solicitud(request, pk):
    """
    Permite derivar una solicitud de forma segura, validando su existencia,
    evitando duplicados y registrando la acción en la bitácora de auditoría.
    """
    # Usar get_object_or_404 previene errores 500 si el ID no existe
    solicitud = get_object_or_404(Solicitud, pk=pk)

    # Validación extra: Evitar doble derivación accidental
    if solicitud.estado == Solicitud.Estado.DERIVADA:
        messages.warning(request, "Esta solicitud ya se encuentra derivada.")
        return redirect("coordinacion:listado")

    # Cambiar estado y guardar
    solicitud.estado = Solicitud.Estado.DERIVADA
    solicitud.save()

    # Registro automático en la bitácora de auditoría (Task 54)
    BitacoraAuditoria.objects.create(
        usuario=request.user,
        accion="Derivación de solicitud",
        detalles=f"La solicitud #{solicitud.pk} fue derivada exitosamente."
    )

    messages.success(request, "Solicitud derivada correctamente.")
    return redirect("coordinacion:listado")