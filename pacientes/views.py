# ============================================
# Task 30: Crear el formulario público y su página
# Dos vistas públicas (sin login): el formulario y la
# página de confirmación.
# ============================================

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.decorators import login_required
from .models import Solicitud
from .forms import SolicitudForm


def nueva_solicitud(request):
    if request.method == "POST":
        form = SolicitudForm(request.POST)
        if form.is_valid():
            # save() normaliza el RUT (ver Solicitud.save).
            form.save()
            messages.success(request, "Tu solicitud fue ingresada correctamente.")
            # Redirigir después del POST evita que al recargar la
            # página se envíe la solicitud dos veces.
            return redirect("pacientes:solicitud_enviada")
    else:
        form = SolicitudForm()
    return render(request, "pacientes/nueva_solicitud.html", {"form": form})


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