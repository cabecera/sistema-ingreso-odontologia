# ============================================
# Task 30: Crear el formulario público y su página
# Dos vistas públicas (sin login): el formulario y la
# página de confirmación.
# ============================================

import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import Group, User
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods

from seguridad.decorators import role_required
from seguridad.inicio import pagina_inicio
from seguridad.models import BitacoraAuditoria

from .models import PerfilPaciente, Solicitud
from .forms import RegistroPacienteForm, SolicitudForm

logger = logging.getLogger(__name__)


def _perfil_del_paciente(user):
    """Perfil ACEPTADO del usuario con sesión, o None (anónimo o personal)."""
    if not user.is_authenticated:
        return None
    perfil = getattr(user, "perfil_paciente", None)
    if perfil is not None and perfil.estado == PerfilPaciente.Estado.ACEPTADO:
        return perfil
    return None


def nueva_solicitud(request):
    # AB#83: con sesión de paciente, los datos personales salen del perfil
    # y la solicitud queda ligada a su cuenta. Sin sesión, sigue siendo
    # el formulario público de siempre.
    perfil = _perfil_del_paciente(request.user)
    # El personal (administrador, coordinador, estudiante) no usa el formulario
    # público: al abrir "/" va directo a su panel. Paciente y anónimo lo ven.
    if request.method == "GET" and request.user.is_authenticated and perfil is None:
        inicio = pagina_inicio(request.user)
        if inicio and not request.user.groups.filter(name="Paciente").exists():
            return redirect(inicio)
    if request.method == "POST":
        form = SolicitudForm(request.POST, perfil=perfil)
        if form.is_valid():
            solicitud = form.save(commit=False)
            if perfil is not None:
                solicitud.paciente = request.user
                solicitud.nombre_completo = perfil.nombre_completo
                solicitud.fecha_nacimiento = perfil.fecha_nacimiento
                solicitud.rut = perfil.rut
                solicitud.telefono = perfil.telefono
            # save() normaliza el RUT (ver Solicitud.save).
            solicitud.save()
            messages.success(request, "Tu solicitud fue ingresada correctamente.")
            if perfil is not None:
                BitacoraAuditoria.objects.create(
                    usuario=request.user,
                    accion="Solicitud ingresada por paciente",
                    detalles=f"Solicitud #{solicitud.pk}.",
                )
                return redirect("pacientes:mis_solicitudes")
            # Redirigir después del POST evita que al recargar la
            # página se envíe la solicitud dos veces.
            return redirect("pacientes:solicitud_enviada")
    else:
        form = SolicitudForm(perfil=perfil)
    return render(
        request, "pacientes/nueva_solicitud.html", {"form": form, "perfil": perfil}
    )


# ============================================
# AB#83 (REQ-17): "Mis solicitudes" del paciente
# --------------------------------------------
# Solo el rol Paciente. Se filtra por la cuenta de la sesión (nunca por
# un id de la URL), así un paciente jamás ve solicitudes ajenas.
# No se muestran datos del estudiante ni antecedentes de salud.
# ============================================
@role_required("Paciente")
def mis_solicitudes(request):
    solicitudes = (
        Solicitud.objects.filter(paciente=request.user)
        .select_related("especialidad", "ficha__especialidad_requerida")
        .order_by("-fecha_creacion")
    )
    return render(request, "pacientes/mis_solicitudes.html", {"solicitudes": solicitudes})


def solicitud_enviada(request):
    return render(request, "pacientes/solicitud_enviada.html")

# ===============================================
# Task 51: Verificar que no vea pacientes ajenos
# ===============================================

@login_required
def detalle_paciente(request, pk):
    # Filtra por el ID (pk) y exige estrictamente que el estudiante asignado 
    # sea el usuario actual logueado. Si es de otro compañero, da 404.
    solicitud = get_object_or_404(Solicitud, pk=pk, estudiante_asignado=request.user)
    return render(request, "pacientes/detalle_paciente.html", {"solicitud": solicitud})


# ============================================
# AB#82 (REQ-17): Registro del paciente con cuenta pendiente
# --------------------------------------------
# - La cuenta se crea INACTIVA: no puede iniciar sesión hasta que el
#   Coordinador la acepte (AB#84).
# - Anti-enumeración: si el correo ya existe, se muestra exactamente la
#   misma página de "registro recibido" y no se crea nada, así nadie
#   puede averiguar qué correos están registrados.
# - La bitácora no guarda datos personales (ni correo ni nombre).
# ============================================
GRUPO_PACIENTE = "Paciente"


def _registrar_paciente(datos):
    """Crea usuario inactivo + perfil. Devuelve True si se creó, False si
    el correo ya estaba registrado."""
    correo = datos["correo"]
    if User.objects.filter(username__iexact=correo).exists():
        # Hash ficticio: iguala el tiempo de respuesta con el de un registro
        # nuevo, para que medir la latencia no revele correos registrados.
        make_password(datos["password1"])
        return False
    try:
        with transaction.atomic():
            usuario = User.objects.create_user(
                username=correo,
                email=correo,
                password=datos["password1"],
                first_name=datos["nombre_completo"][:150],
                is_active=False,
            )
            grupo, _ = Group.objects.get_or_create(name=GRUPO_PACIENTE)
            usuario.groups.add(grupo)
            perfil = PerfilPaciente.objects.create(
                usuario=usuario,
                nombre_completo=datos["nombre_completo"],
                fecha_nacimiento=datos["fecha_nacimiento"],
                rut=datos["rut"],
                telefono=datos["telefono"],
            )
            BitacoraAuditoria.objects.create(
                usuario=None,
                accion="Registro de paciente",
                detalles=f"Perfil de paciente #{perfil.pk} queda pendiente de revisión.",
            )
    except IntegrityError:
        # Dos registros simultáneos con el mismo correo: gana el primero.
        # Cualquier otro error de integridad NO se oculta: se propaga (500).
        if User.objects.filter(username__iexact=correo).exists():
            return False
        raise
    return True


def _avisar_registro_recibido(correo):
    """Aviso por correo. Render Free bloquea SMTP, por eso el backend por
    defecto es "console" (el aviso queda en el log). Si falla el envío, el
    registro no se pierde."""
    try:
        send_mail(
            subject="Recibimos tu registro - Facultad de Odontología",
            message=(
                "Hola,\n\n"
                "Recibimos tu registro en el sistema de ingreso de la clínica "
                "odontológica. La coordinación lo revisará y, en un plazo de "
                "48 horas, recibirás un correo con el resultado de la revisión.\n\n"
                "Si no fuiste tú, puedes ignorar este mensaje."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[correo],
        )
    except Exception:  # noqa: BLE001 - un fallo de correo no debe romper el registro
        logger.warning("No se pudo enviar el aviso de registro.")


@require_http_methods(["GET", "POST"])
def registro_paciente(request):
    if request.method == "POST":
        form = RegistroPacienteForm(request.POST)
        if form.is_valid():
            creado = _registrar_paciente(form.cleaned_data)
            if creado:
                _avisar_registro_recibido(form.cleaned_data["correo"])
            return redirect("pacientes:registro_enviado")
    else:
        form = RegistroPacienteForm()
    return render(request, "pacientes/registro_paciente.html", {"form": form})


def registro_enviado(request):
    return render(request, "pacientes/registro_enviado.html")
