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