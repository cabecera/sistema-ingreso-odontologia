from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from seguridad.decorators import role_required

# Agrega el decorador encima de las vistas privadas de estudiantes.
# Por ejemplo, vistas para ingresar o revisar evaluaciones, fichas o alumnos:

@role_required('Administrador', 'Coordinador', 'Docente', 'Estudiante')
def panel_estudiantes(request):
    """
    Vista accesible para perfiles autorizados en el módulo de estudiantes.
    """
    return render(request, 'estudiantes/index.html')


