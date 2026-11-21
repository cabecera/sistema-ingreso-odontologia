from django.db import migrations, models

from pacientes.rut_login import hash_rut


def rellenar_hash(apps, schema_editor):
    """Pacientes ya registrados: calcula su índice de RUT para que puedan
    ingresar con él. Si el RUT no se puede leer (cifrado con otra clave) o
    está repetido, se deja vacío en vez de fallar."""
    Perfil = apps.get_model("pacientes", "PerfilPaciente")
    usados = set()
    for perfil in Perfil.objects.order_by("pk"):
        valor = hash_rut(perfil.rut)
        if valor and valor not in usados:
            perfil.rut_hash = valor
            perfil.save(update_fields=["rut_hash"])
            usados.add(valor)


class Migration(migrations.Migration):

    dependencies = [
        ("pacientes", "0009_fichaclinica"),
    ]

    operations = [
        migrations.AddField(
            model_name="perfilpaciente",
            name="rut_hash",
            field=models.CharField(blank=True, editable=False, max_length=64, null=True, unique=True),
        ),
        migrations.RunPython(rellenar_hash, migrations.RunPython.noop),
    ]
