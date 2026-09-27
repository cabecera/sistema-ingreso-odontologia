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


def validar_fecha_nacimiento(valor: date) -> None:
    """
    Verifica que la fecha de nacimiento sea razonable: ni futura
    ni más antigua que 120 años. Evita errores de tipeo del
    paciente (por ejemplo, invertir día y mes).
    """
    hoy = date.today()
    if valor > hoy:
        raise ValidationError("La fecha de nacimiento no puede ser futura.")
    if valor.year < hoy.year - 120:
        raise ValidationError("Revisa la fecha de nacimiento ingresada.")
