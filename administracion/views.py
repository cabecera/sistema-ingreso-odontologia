from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render

from seguridad.decorators import role_required
from seguridad.models import BitacoraAuditoria

from administracion.models import Especialidad

from .forms import EspecialidadForm, UsuarioNuevoForm

@role_required('Super Administrador')
def panel_administracion(request):
    """
    Vista de administracion restringida exclusivamente para el rol Super Administrador.
    """
    return render(request, 'administracion/index.html')


# ============================================
# Task 59: Gestión de usuarios (REQ-14)
# --------------------------------------------
# Solo el Super Administrador. Crear y activar/desactivar cuentas del
# personal. Desactivar (no borrar) conserva el historial: las
# derivaciones y la bitácora siguen apuntando a la cuenta. Cada acción
# deja una fila en BitacoraAuditoria, sin contraseñas ni datos sensibles.
# ============================================
@role_required('Super Administrador')
def lista_usuarios(request):
    usuarios = (
        get_user_model().objects
        .prefetch_related('groups')
        .order_by('username')
    )
    return render(request, 'administracion/usuarios.html', {'usuarios': usuarios})


@role_required('Super Administrador')
def usuario_nuevo(request):
    if request.method == 'POST':
        form = UsuarioNuevoForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                usuario = form.save()
                BitacoraAuditoria.objects.create(
                    usuario=request.user,
                    accion="Creación de usuario",
                    detalles=(
                        f"Usuario '{usuario.get_username()}' creado con el rol "
                        f"'{form.cleaned_data['rol']}'."
                    ),
                )
            messages.success(request, "Usuario creado correctamente.")
            return redirect('administracion:usuarios')
    else:
        form = UsuarioNuevoForm()
    return render(request, 'administracion/usuario_form.html', {'form': form})


@role_required('Super Administrador')
def usuario_cambiar_estado(request, pk):
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    usuario = get_object_or_404(get_user_model(), pk=pk)

    if usuario.pk == request.user.pk:
        messages.error(request, "No puedes desactivar tu propia cuenta.")
        return redirect('administracion:usuarios')
    if usuario.is_superuser:
        messages.error(request, "Una cuenta de superusuario no se gestiona desde aquí.")
        return redirect('administracion:usuarios')

    with transaction.atomic():
        usuario.is_active = not usuario.is_active
        usuario.save(update_fields=['is_active'])
        BitacoraAuditoria.objects.create(
            usuario=request.user,
            accion="Activación de usuario" if usuario.is_active else "Desactivación de usuario",
            detalles=f"Usuario '{usuario.get_username()}' (id {usuario.pk}).",
        )

    messages.success(
        request,
        "Usuario activado." if usuario.is_active else "Usuario desactivado.",
    )
    return redirect('administracion:usuarios')


# ============================================
# Task 60: Gestión de especialidades (REQ-14)
# --------------------------------------------
# Solo el Super Administrador. No hay "borrar": una especialidad con
# solicitudes está protegida (on_delete=PROTECT) y además se quiere
# conservar el historial. Se desactiva y deja de ofrecerse en el
# formulario público (ver pacientes/forms.py). Cada cambio queda en la
# bitácora.
# ============================================
@role_required('Super Administrador')
def lista_especialidades(request):
    especialidades = Especialidad.objects.annotate(
        total_solicitudes=Count('solicitudes')
    ).order_by('nombre')
    return render(
        request,
        'administracion/especialidades.html',
        {'especialidades': especialidades},
    )


def _guardar_especialidad(request, form, accion, mensaje):
    with transaction.atomic():
        especialidad = form.save()
        BitacoraAuditoria.objects.create(
            usuario=request.user,
            accion=accion,
            detalles=f"Especialidad '{especialidad.nombre}' (id {especialidad.pk}).",
        )
    messages.success(request, mensaje)
    return redirect('administracion:especialidades')


@role_required('Super Administrador')
def especialidad_nueva(request):
    if request.method == 'POST':
        form = EspecialidadForm(request.POST)
        if form.is_valid():
            return _guardar_especialidad(
                request, form, "Creación de especialidad",
                "Especialidad creada correctamente.",
            )
    else:
        form = EspecialidadForm(initial={'activa': True})
    return render(
        request,
        'administracion/especialidad_form.html',
        {'form': form, 'titulo': 'Nueva especialidad'},
    )


@role_required('Super Administrador')
def especialidad_editar(request, pk):
    especialidad = get_object_or_404(Especialidad, pk=pk)
    if request.method == 'POST':
        form = EspecialidadForm(request.POST, instance=especialidad)
        if form.is_valid():
            return _guardar_especialidad(
                request, form, "Edición de especialidad",
                "Especialidad actualizada correctamente.",
            )
    else:
        form = EspecialidadForm(instance=especialidad)
    return render(
        request,
        'administracion/especialidad_form.html',
        {'form': form, 'titulo': 'Editar especialidad'},
    )


@role_required('Super Administrador')
def especialidad_cambiar_estado(request, pk):
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    especialidad = get_object_or_404(Especialidad, pk=pk)
    with transaction.atomic():
        especialidad.activa = not especialidad.activa
        especialidad.save(update_fields=['activa'])
        BitacoraAuditoria.objects.create(
            usuario=request.user,
            accion=(
                "Activación de especialidad" if especialidad.activa
                else "Desactivación de especialidad"
            ),
            detalles=f"Especialidad '{especialidad.nombre}' (id {especialidad.pk}).",
        )
    messages.success(
        request,
        "Especialidad activada." if especialidad.activa else "Especialidad desactivada.",
    )
    return redirect('administracion:especialidades')
