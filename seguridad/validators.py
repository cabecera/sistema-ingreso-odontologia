# ============================================
# Política de contraseñas (REQ-10 / REQ-03)
# --------------------------------------------
# Se suma a los validadores de Django (parecido al usuario, contraseñas
# comunes, solo números, largo mínimo): exige mayúscula, minúscula, número y
# símbolo, y un largo máximo de 50 para que nadie fuerce al servidor a calcular
# hashes de textos enormes (denegación de servicio).
# ============================================
from django.core.exceptions import ValidationError

LARGO_MAXIMO = 50


class ComplejidadValidator:
    def validate(self, password, user=None):
        errores = []
        if len(password) > LARGO_MAXIMO:
            errores.append(f"La contraseña no puede tener más de {LARGO_MAXIMO} caracteres.")
        if not any(c.isupper() for c in password):
            errores.append("Debe incluir al menos una letra mayúscula.")
        if not any(c.islower() for c in password):
            errores.append("Debe incluir al menos una letra minúscula.")
        if not any(c.isdigit() for c in password):
            errores.append("Debe incluir al menos un número.")
        if all(c.isalnum() or c.isspace() for c in password):
            errores.append("Debe incluir al menos un símbolo (por ejemplo ! # $ % & * -).")
        if errores:
            raise ValidationError(errores, code="password_complejidad")

    def get_help_text(self):
        return (
            f"De 10 a {LARGO_MAXIMO} caracteres, con mayúscula, minúscula, número y símbolo."
        )
