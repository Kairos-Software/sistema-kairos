from django.db import migrations, models


def calcular_redondeos(apps, schema_editor):
    """
    Calcula el redondeo de las recaudaciones ya cargadas (diferencia entre lo
    que tiene el sistema y lo que se declaró, cuando es un redondeo creíble).
    Usa la misma función que la app para no duplicar la regla. Solo recorre
    recaudaciones existentes: en una base vacía no hace nada.
    """
    RecaudacionDiaria = apps.get_model('cobranzas', 'RecaudacionDiaria')
    if not RecaudacionDiaria.objects.exists():
        return
    from areas.cobranzas.views_recaudaciones import recalcular_redondeo_recaudaciones
    recalcular_redondeo_recaudaciones()


class Migration(migrations.Migration):

    dependencies = [
        ('cobranzas', '0025_redondeo_y_comision'),
    ]

    operations = [
        migrations.AddField(
            model_name='recaudaciondiaria',
            name='redondeo',
            field=models.DecimalField(
                decimal_places=2, default=0, max_digits=12,
                help_text='Redondeo que quedó dentro de las facturas ese día '
                          '(sistema − lo declarado). Se calcula solo.'),
        ),
        migrations.RunPython(calcular_redondeos, migrations.RunPython.noop),
    ]
