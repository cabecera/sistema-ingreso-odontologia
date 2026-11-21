
# Task 30: 

from django.urls import path

from . import views

app_name = "pacientes"

urlpatterns = [
    # La página de inicio es el formulario: es lo que ve el paciente.
    path("", views.nueva_solicitud, name="nueva_solicitud"),
    path("mis-solicitudes/", views.mis_solicitudes, name="mis_solicitudes"),
    path("registro/", views.registro_paciente, name="registro"),
    path("registro/enviado/", views.registro_enviado, name="registro_enviado"),
    path('detalle/<int:pk>/', views.detalle_paciente, name='detalle_paciente'),
]