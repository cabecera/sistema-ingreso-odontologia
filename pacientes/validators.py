# ============================================
# Task 29: Crear modelo de Solicitud y su tabla
# Issue padre: REQ-01 (Registro público de solicitud)
# --------------------------------------------
# Funciones de validación usadas por pacientes/models.py.
# Se separan del modelo para poder reutilizarlas después en
# el formulario público (tarea #30, Carlos) sin duplicar código:
# el formulario puede llamar a estas mismas funciones para avisarle
# al paciente el error ANTES de intentar guardar en la base.
# ============================================

from datetime import date

from django.core.exceptions import ValidationError


def limpiar_rut(valor: str) -> str:
    """
    Quita puntos, guiones y espacios, y deja la K en mayúscula.

    Ejemplo: "12.345.678-5" -> "123456785"
    Se usa como paso previo tanto para validar como para formatear,
    así los dos procesos parten siempre del mismo texto limpio.
    """
    return valor.replace(".", "").replace("-", "").replace(" ", "").upper()


def calcular_dv(cuerpo: str) -> str:
    """
    Calcula el dígito verificador de un RUT chileno (algoritmo módulo 11).

    "cuerpo" es el RUT sin el dígito verificador (por ejemplo "12345678").
    Se usa dentro de validar_rut() para comprobar que el DV que escribió
    el paciente coincide con el que corresponde matemáticamente.
    """
    suma = 0
    multiplicador = 2
    for digito in reversed(cuerpo):
        suma += int(digito) * multiplicador
        multiplicador = 2 if multiplicador == 7 else multiplicador + 1
    resto = 11 - (suma % 11)
    if resto == 11:
        return "0"
    if resto == 10:
        return "K"
    return str(resto)


def formatear_rut(valor: str) -> str:
    """
    Devuelve el RUT en formato uniforme: 12345678-5 (sin puntos).

    Se llama desde Solicitud.save() para que en la base de datos
    todos los RUT queden guardados exactamente igual, sin importar
    cómo los haya tipeado cada paciente en el formulario.
    """
    rut = limpiar_rut(valor)
    return f"{rut[:-1]}-{rut[-1]}"


def validar_rut(valor: str) -> None:
    """
    Verifica que el RUT sea válido: largo correcto y dígito
    verificador correcto. Lanza ValidationError si no lo es,
    que es lo que Django espera de un validador de campo.
    """
    rut = limpiar_rut(valor)
    if len(rut) < 8 or len(rut) > 9 or not rut[:-1].isdigit():
        raise ValidationError("Ingresa un RUT válido, por ejemplo 12.345.678-5.")
    cuerpo, dv = rut[:-1], rut[-1]
    if calcular_dv(cuerpo) != dv:
        raise ValidationError("El RUT no es válido. Revisa el dígito verificador.")


EDAD_MAXIMA = 120
EDAD_MINIMA_REGISTRO = 18


def _hace_anios(anios: int, hoy: date | None = None) -> date:
    """Fecha de hace N años exactos (29 de febrero -> 28 de febrero)."""
    hoy = hoy or date.today()
    try:
        return hoy.replace(year=hoy.year - anios)
    except ValueError:
        return hoy.replace(year=hoy.year - anios, day=28)


def limites_fecha_nacimiento(edad_minima: int = 0):
    """(más antigua, más reciente) permitidas; se usan también como min/max del calendario."""
    return _hace_anios(EDAD_MAXIMA), _hace_anios(edad_minima)


def validar_fecha_nacimiento(valor: date) -> None:
    """
    Verifica que la fecha de nacimiento sea razonable: ni futura
    ni de hace más de 120 años. Evita errores de tipeo del
    paciente (por ejemplo, el año 1800).
    """
    if valor > date.today():
        raise ValidationError("La fecha de nacimiento no puede ser futura.")
    if valor < _hace_anios(EDAD_MAXIMA):
        raise ValidationError(
            f"La fecha de nacimiento no puede ser de hace más de {EDAD_MAXIMA} años."
        )


def validar_mayor_de_edad(valor: date) -> None:
    """Para crear una cuenta de paciente: al menos 18 años cumplidos."""
    if valor > _hace_anios(EDAD_MINIMA_REGISTRO):
        raise ValidationError(
            f"Debes ser mayor de {EDAD_MINIMA_REGISTRO} años para registrarte."
        )
