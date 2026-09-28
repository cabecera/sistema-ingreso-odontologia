"""
URL configuration for core project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""


# --------------------------------------------
# Enrutador principal del proyecto. Delega las
# rutas públicas (el formulario del paciente) a
# la app "pacientes". El admin de Django queda
# accesible en /admin/.
# ============================================

from django.contrib import admin
from django.urls import include,path

urlpatterns = [
    path('admin/', admin.site.urls),


    # Delega todo lo demás a pacientes/urls.py.
    # La página de inicio (path "") será el formulario.
    path('', include('pacientes.urls')),
]


