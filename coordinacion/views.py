from datetime import date, datetime, time, timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
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
# ============================================
# Task 48: Filtros de búsqueda del listado (REQ-04)
# --------------------------------------------
# Filtros opcionales por GET: especialidad, fecha de ingreso y
# estado. Los parámetros vienen del usuario, así que NUNCA se
# usan tal cual: cada uno se valida en el servidor y, si no es
# válido, se ignora (el listado no se rompe ni refleja el texto).
#   - especialidad: debe ser el id de una especialidad del catálogo.
#   - fecha: debe ser una fecha ISO válida (AAAA-MM-DD).
#   - estado: debe ser uno de Solicitud.Estado.
# ============================================
def _rango_del_dia(fecha):
    """Inicio y fin (excluyente) del día en la zona horaria del sitio.

    Se filtra por rango y no con __date porque en MySQL ese lookup usa
    CONVERT_TZ, que devuelve NULL si el servidor no tiene cargadas las
    tablas de zonas horarias (no se puede asegurar en un MySQL gestionado).
    """
    inicio = timezone.make_aware(datetime.combine(fecha, time.min))
    fin = timezone.make_aware(datetime.combine(fecha + timedelta(days=1), time.min))
    return inicio, fin


# Horario de atención (REQ-18): debe ser futuro y dentro de un año.
MAX_DIAS_ATENCION = 365


def _leer_fecha_atencion(texto):
    """
    Convierte el valor de un <input type="datetime-local"> en una fecha
    con zona horaria. Devuelve None si no es válida, ya pasó o está
    demasiado lejos. El navegador no es de fiar: se valida acá.
    """
    try:
        naive = datetime.fromisoformat((texto or "").strip())
    except (ValueError, OverflowError):
        return None
    if naive.tzinfo is not None:
        return None
    try:
        fecha = timezone.make_aware(naive)
    except (ValueError, OverflowError):
        return None
    ahora = timezone.now()
    if fecha <= ahora or fecha > ahora + timedelta(days=MAX_DIAS_ATENCION):
        return None
    return fecha


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
    # REALIZADO y TERMINADO también deben verse: si no, desaparecerían.
    atendidas = solicitudes.filter(
        estado__in=[Solicitud.Estado.REALIZADO, Solicitud.Estado.TERMINADO]
    )

    return render(
        request,
        "coordinacion/listado.html",
        {
            "pendientes": pendientes,
            "derivadas": derivadas,
            "atendidas": atendidas,
            # Valor mínimo del selector de horario (hora local, sin segundos).
            "min_atencion": timezone.localtime().strftime("%Y-%m-%dT%H:%M"),
            "especialidades": especialidades,
            # Candidatos del selector "Derivar a": solo cuentas activas con
            # rol Estudiante (la vista de derivación vuelve a validarlo).
            "estudiantes": get_user_model().objects.filter(
                groups__name="Estudiante", is_active=True
            ).order_by("username"),
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
# Tasks 52 y 54: Derivación formal y registro de auditoría (REQ-05)
# --------------------------------------------
# Solo POST (cambia datos; un enlace GET permitiría CSRF). Dentro de una
# transacción se bloquea la fila para que dos coordinadores no deriven la
# misma solicitud a la vez, y la solicitud y la bitácora se guardan juntas
# o no se guarda ninguna. La bitácora no incluye datos del paciente
# (minimización de datos): solo el número de solicitud y el estudiante.
# ============================================
@role_required('Super Administrador', 'Coordinador')
def derivar_solicitud(request, pk):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    estudiante_id = request.POST.get("estudiante_asignado", "").strip()
    user_model = get_user_model()

    try:
        estudiante_pk = user_model._meta.pk.to_python(estudiante_id)
    except (ValidationError, TypeError, ValueError):
        estudiante_pk = None

    estudiante = None
    if estudiante_pk is not None:
        estudiante = user_model.objects.filter(
            pk=estudiante_pk,
            groups__name="Estudiante",
            is_active=True,
        ).first()

    # Una solicitud inexistente es 404 antes de evaluar el estudiante.
    get_object_or_404(Solicitud, pk=pk)

    if estudiante is None:
        messages.error(request, "Selecciona un usuario con rol de estudiante.")
        return redirect("coordinacion:listado_solicitudes")

    fecha_atencion = _leer_fecha_atencion(request.POST.get("fecha_atencion"))
    if fecha_atencion is None:
        messages.error(
            request,
            "Indica una fecha y hora de atención futura (máximo un año).",
        )
        return redirect("coordinacion:listado_solicitudes")

    with transaction.atomic():
        solicitud = get_object_or_404(Solicitud.objects.select_for_update(), pk=pk)

        if not solicitud.puede_pasar_a(Solicitud.Estado.DERIVADA):
            messages.warning(request, "Esta solicitud ya fue derivada.")
            return redirect("coordinacion:listado_solicitudes")

        solicitud.estudiante_asignado = estudiante
        solicitud.estado = Solicitud.Estado.DERIVADA
        solicitud.derivado_por = request.user
        solicitud.fecha_derivacion = timezone.now()
        solicitud.fecha_atencion = fecha_atencion
        solicitud.save()

        BitacoraAuditoria.objects.create(
            usuario=request.user,
            accion="Derivación de solicitud",
            detalles=(
                f"Solicitud #{solicitud.pk} derivada al estudiante "
                f"'{estudiante.get_username()}' (id {estudiante.pk}), atención el "
                f"{timezone.localtime(fecha_atencion):%d-%m-%Y %H:%M}."
            ),
        )

    messages.success(request, "Solicitud derivada y registrada correctamente.")
    return redirect("coordinacion:listado_solicitudes")
