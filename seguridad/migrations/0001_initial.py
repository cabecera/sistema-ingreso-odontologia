# ============================================
# Task 34: Crear los roles internos del sistema
# Issue padre: REQ-07 (Control de acceso basado en roles)
# --------------------------------------------
# Esta migración crea los 3 perfiles internos del sistema
# (Coordinador, Estudiante, Super Administrador) como
# Django Groups. No se crean a mano en el admin porque
# así quedan versionados en Git y se recrean solos en
# cualquier entorno nuevo (incluyendo Azure en producción).
#
# La asignación de PERMISOS específicos a cada grupo
# (qué puede ver/hacer cada uno) es responsabilidad de la
# Task 35, no de esta.
# ============================================
from django.db import migrations


def crear_grupos(apps, schema_editor):
    # Usamos apps.get_model (no el import directo de Group)
    # porque así Django usa la versión del modelo que
    # corresponde exactamente a este punto de la migración,
    # no a la versión actual del código.
    Group = apps.get_model('auth', 'Group')

    for nombre in ['Coordinador', 'Estudiante', 'Super Administrador']:
        Group.objects.get_or_create(name=nombre)


def eliminar_grupos(apps, schema_editor):
    # Función inversa: permite revertir esta migración
    # (python manage.py migrate seguridad 000X_anterior)
    # sin dejar basura si algo sale mal.
    Group = apps.get_model('auth', 'Group')
    Group.objects.filter(
        name__in=['Coordinador', 'Estudiante', 'Super Administrador']
    ).delete()


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.RunPython(crear_grupos, eliminar_grupos),
    ]
