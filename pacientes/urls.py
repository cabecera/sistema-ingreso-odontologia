
# Task 30: 

from django.urls import path

from . import views

app_name = "pacientes"

urlpatterns = [
    # La página de inicio es el formulario: es lo que ve el paciente.
    path("", views.nueva_solicitud, name="nueva_solicitud"),
    path("solicitud/enviada/", views.solicitud_enviada, name="solicitud_enviada"),
]