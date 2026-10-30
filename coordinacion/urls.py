from django.urls import path
from . import views

app_name = "coordinacion"

urlpatterns = [
    path("listado/", views.listado_solicitudes, name="listado_solicitudes"),
]