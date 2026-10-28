from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from pacientes.models import Solicitud
from seguridad.decorators import role_required


@role_required('Super Administrador', 'Coordinador', 'Estudiante')
def panel_estudiantes(request):
    """
    Vista accesible para perfiles autorizados en el módulo de estudiantes.
    """
    return render(request, 'estudiantes/index.html')


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
