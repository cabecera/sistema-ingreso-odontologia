from datetime import date

from django.core.exceptions import ValidationError


def limpiar_rut(valor: str) -> str:
    """Quita puntos, guion y espacios, y deja la K en mayúscula."""
    return valor.replace(".", "").replace("-", "").replace(" ", "").upper()


def calcular_dv(cuerpo: str) -> str:
    """Calcula el dígito verificador (módulo 11) de un RUT chileno."""
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
    """Devuelve el RUT en formato uniforme: 12345678-5 (sin puntos)."""
    rut = limpiar_rut(valor)
    return f"{rut[:-1]}-{rut[-1]}"


def validar_rut(valor: str) -> None:
    rut = limpiar_rut(valor)
    if len(rut) < 8 or len(rut) > 9 or not rut[:-1].isdigit():
        raise ValidationError("Ingresa un RUT válido, por ejemplo 12.345.678-5.")
    cuerpo, dv = rut[:-1], rut[-1]
    if calcular_dv(cuerpo) != dv:
        raise ValidationError("El RUT no es válido. Revisa el dígito verificador.")


def validar_fecha_nacimiento(valor: date) -> None:
    hoy = date.today()
    if valor > hoy:
        raise ValidationError("La fecha de nacimiento no puede ser futura.")
    if valor.year < hoy.year - 120:
        raise ValidationError("Revisa la fecha de nacimiento ingresada.")
