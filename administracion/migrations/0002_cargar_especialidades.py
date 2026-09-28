# ============================================
# Task 32: Crear catálogo de especialidades
# Issue padre: REQ-02 (Selección de especialidad)
# --------------------------------------------
# Carga las 9 especialidades fijas del REQ-02. Se hace por
# migración para que queden versionadas en Git y se recreen
# solas en cualquier entorno, incluyendo Azure.
#
# Historial: el primer commit subió este archivo generado por
# --empty sin el código de RunPython (quedó sin guardar en el
# editor antes del commit), por lo que operations quedaba vacío
# y el selector de especialidades no se cargaba en un clon nuevo
# del repo. Guido lo detectó al probar el PR desde cero (AB#30).
# Se corrigió agregando la lógica real y se verificó revirtiendo
# y reaplicando la migración en local: la tabla queda en 0 filas
# al revertir y vuelve a las 9 especialidades al reaplicar.
# ============================================

from django.db import migrations

ESPECIALIDADES = [
    "Caries",
    "Periodoncia",
    "Operatoria",
    "Endodoncia",
    "Prótesis fija",
    "Prótesis removible",
    "Ortodoncia",
    "Implantología",
    "Cirugía",
]


def cargar_especialidades(apps, schema_editor):
    # get_or_create evita duplicar si la migración se repite.
    Especialidad = apps.get_model("administracion", "Especialidad")
    for nombre in ESPECIALIDADES:
        Especialidad.objects.get_or_create(nombre=nombre)


def quitar_especialidades(apps, schema_editor):
    # Función inversa, para poder revertir la migración.
    Especialidad = apps.get_model("administracion", "Especialidad")
    Especialidad.objects.filter(nombre__in=ESPECIALIDADES).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("administracion", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(cargar_especialidades, quitar_especialidades),
    ]