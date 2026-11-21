from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponseNotAllowed
from django.urls import reverse
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.decorators import login_required

from .forms import FichaClinicaForm
from pacientes.models import FichaClinica, Solicitud
from seguridad.decorators import role_required
from seguridad.models import BitacoraAuditoria


@role_required('Super Administrador', 'Coordinador', 'Estudiante')
def panel_estudiantes(request):
    """
    Panel del estudiante: resumen de SUS casos. El filtro usa request.user
    (nunca un id de la URL), así no se ven pacientes de otro estudiante.
    """
    mias = Solicitud.objects.filter(estudiante_asignado=request.user)
    conteos = mias.aggregate(
        por_atender=Count('pk', filter=Q(estado=Solicitud.Estado.DERIVADA)),
        por_ficha=Count('pk', filter=Q(estado=Solicitud.Estado.REALIZADO)),
        terminadas=Count('pk', filter=Q(estado=Solicitud.Estado.TERMINADO)),
    )
    proximas = (
        mias.exclude(estado=Solicitud.Estado.TERMINADO)
        .select_related('especialidad')
        .order_by('fecha_atencion', 'fecha_creacion')[:5]
    )
    return render(request, 'estudiantes/index.html', {'conteos': conteos, 'proximas': proximas})


# Task 50 / REQ-06
@role_required('Estudiante')
def mis_pacientes(request):
    """
    Lista SOLO las solicitudes derivadas al estudiante que inició sesión.

    El filtro usa request.user (nunca un id recibido por URL o GET), así un
    estudiante no puede ver pacientes de otro cambiando un parámetro (IDOR).
    Se omiten los antecedentes de salud: la tabla solo necesita RUT, nombre,
    especialidad y fecha (minimización de datos).
    """
    solicitudes = (
        Solicitud.objects
        .filter(estudiante_asignado=request.user)
        .select_related('especialidad')
    )
    return render(
        request,
        'estudiantes/mis_pacientes.html',
        {'solicitudes': solicitudes},
    )


# ============================================
# Task 86 / REQ-18: el estudiante marca la atención como realizada
# --------------------------------------------
# Solo POST. get_object_or_404 filtra por request.user: marcar el
# paciente de otro estudiante da 404 (anti-IDOR, igual que "mis
# pacientes"). La transición se valida contra el ciclo de vida del
# modelo y deja registro en la bitácora.
# ============================================
@role_required('Estudiante')
def marcar_realizada(request, pk):
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    with transaction.atomic():
        solicitud = get_object_or_404(
            Solicitud.objects.select_for_update(),
            pk=pk,
            estudiante_asignado=request.user,
        )
        if not solicitud.puede_pasar_a(Solicitud.Estado.REALIZADO):
            messages.error(request, "Esta atención no se puede marcar como realizada.")
            return redirect('estudiantes:mis_pacientes')

        solicitud.estado = Solicitud.Estado.REALIZADO
        solicitud.save(update_fields=['estado'])
        BitacoraAuditoria.objects.create(
            usuario=request.user,
            accion="Atención realizada",
            detalles=f"Solicitud #{solicitud.pk} marcada como REALIZADO.",
        )

    messages.success(request, "Atención marcada como realizada.")
    return redirect('estudiantes:mis_pacientes')


# ============================================
# AB#87 / REQ-18: ficha clínica, examen previo y reporte
# --------------------------------------------
# Solo el estudiante asignado (si no, 404: anti-IDOR). Solo cuando la
# atención ya está REALIZADA. Al guardar, la solicitud pasa a TERMINADO
# en la misma transacción y la ficha ya no se puede cambiar. La bitácora
# guarda solo el número de solicitud, nunca contenido clínico.
# ============================================
@role_required('Estudiante')
def completar_ficha(request, pk):
    solicitud = get_object_or_404(Solicitud, pk=pk, estudiante_asignado=request.user)

    if solicitud.estado == Solicitud.Estado.TERMINADO:
        return redirect('estudiantes:ver_reporte', pk=solicitud.pk)
    if solicitud.estado != Solicitud.Estado.REALIZADO:
        messages.error(request, "Primero marca la atención como realizada.")
        return redirect('estudiantes:mis_pacientes')

    if request.method == 'POST':
        form = FichaClinicaForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                # Se vuelve a leer con bloqueo: dos envíos a la vez no
                # pueden crear dos fichas ni terminar la solicitud dos veces.
                solicitud = get_object_or_404(
                    Solicitud.objects.select_for_update(),
                    pk=pk,
                    estudiante_asignado=request.user,
                )
                if not solicitud.puede_pasar_a(Solicitud.Estado.TERMINADO):
                    messages.error(request, "Esta ficha ya fue completada.")
                    return redirect('estudiantes:mis_pacientes')

                ficha = form.save(commit=False)
                ficha.solicitud = solicitud
                ficha.estudiante = request.user
                ficha.save()
                solicitud.estado = Solicitud.Estado.TERMINADO
                solicitud.save(update_fields=['estado'])
                BitacoraAuditoria.objects.create(
                    usuario=request.user,
                    accion="Ficha clínica completada",
                    detalles=f"Solicitud #{solicitud.pk} marcada como TERMINADO.",
                )
            messages.success(request, "Ficha guardada: la atención quedó terminada.")
            return redirect('estudiantes:ver_reporte', pk=solicitud.pk)
    else:
        form = FichaClinicaForm()

    return render(
        request,
        'estudiantes/ficha_form.html',
        {'form': form, 'solicitud': solicitud},
    )


@role_required('Estudiante')
def ver_reporte(request, pk):
    solicitud = get_object_or_404(
        Solicitud.objects.select_related('especialidad', 'ficha__especialidad_requerida'),
        pk=pk,
        estudiante_asignado=request.user,
        estado=Solicitud.Estado.TERMINADO,
    )
    return render(request, 'estudiantes/reporte.html', {
        'solicitud': solicitud,
        'ficha': solicitud.ficha,
        'volver_url': reverse('estudiantes:mis_pacientes'),
    })
