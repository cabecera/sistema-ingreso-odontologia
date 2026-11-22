# ============================================
# Navegación según el rol del usuario
# --------------------------------------------
# Deja disponible en todas las plantillas la variable "menu", con un
# booleano por cada grupo de enlaces del menú superior. Es solo para
# MOSTRAR enlaces: la seguridad real sigue estando en @role_required de
# cada vista (un enlace oculto no protege nada, y uno visible no da acceso).
# ============================================


from .inicio import pagina_inicio


def menu_por_rol(request):
    usuario = request.user
    if not usuario.is_authenticated:
        return {"menu": {}, "inicio_url": "/"}
    roles = set(usuario.groups.values_list("name", flat=True))
    return {
        "inicio_url": pagina_inicio(usuario) or "/",
        "menu": {
            "paciente": "Paciente" in roles,
            "coordinacion": usuario.is_superuser or bool(roles & {"Coordinador", "Super Administrador"}),
            "estudiante": "Estudiante" in roles,
            "administracion": usuario.is_superuser or "Super Administrador" in roles,
        }
    }


def csp(request):
    """Nonce de la política de seguridad de contenido (lo usa el <style> de base.html)."""
    return {"csp_nonce": getattr(request, "csp_nonce", "")}
