# ============================================
# Navegación según el rol del usuario
# --------------------------------------------
# Deja disponible en todas las plantillas la variable "menu", con un
# booleano por cada grupo de enlaces del menú superior. Es solo para
# MOSTRAR enlaces: la seguridad real sigue estando en @role_required de
# cada vista (un enlace oculto no protege nada, y uno visible no da acceso).
# ============================================


def menu_por_rol(request):
    usuario = request.user
    if not usuario.is_authenticated:
        return {"menu": {}}
    roles = set(usuario.groups.values_list("name", flat=True))
    return {
        "menu": {
            "paciente": "Paciente" in roles,
            "coordinacion": usuario.is_superuser or bool(roles & {"Coordinador", "Super Administrador"}),
            "estudiante": "Estudiante" in roles,
            "administracion": usuario.is_superuser or "Super Administrador" in roles,
        }
    }
