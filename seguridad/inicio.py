# ============================================
# Página principal de cada rol
# --------------------------------------------
# Un solo lugar define a dónde "pertenece" cada rol. Lo usan el login (destino
# al entrar), el logo del menú ("Facultad de Odontología") y el formulario
# público (el personal que abre "/" va a su panel en vez de ver el formulario).
# ============================================
from django.urls import reverse


def pagina_inicio(usuario):
    """URL de la página principal del usuario, o None si no tiene un rol."""
    if not usuario.is_authenticated:
        return None
    roles = set(usuario.groups.values_list("name", flat=True))
    if usuario.is_superuser or "Super Administrador" in roles:
        return reverse("administracion:panel")
    if "Coordinador" in roles:
        return reverse("coordinacion:panel")
    if "Estudiante" in roles:
        return reverse("estudiantes:panel")
    if "Paciente" in roles:
        return reverse("pacientes:mis_solicitudes")
    return None
