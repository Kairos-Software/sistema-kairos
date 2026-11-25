from django.db import migrations


def recalcular(apps, schema_editor):
    """
    Vuelve a calcular RecaudacionDiaria.redondeo con las reglas corregidas:
      - tope de $100 por boleta redonda (antes $1.000: tomaba como redondeo
        diferencias que no lo eran, ej. RapiPago 19/10/2026 $8.311,91);
      - PagoFácil declara todo menos lo cobrado con tarjeta en su terminal
        (antes "solo efectivo": dejaba afuera las transferencias).
    No cambia ningún cobro ni el monto de ninguna recaudación: solo ese campo.
    """
    RecaudacionDiaria = apps.get_model('cobranzas', 'RecaudacionDiaria')
    if not RecaudacionDiaria.objects.exists():
        return
    from areas.cobranzas.views_recaudaciones import recalcular_redondeo_recaudaciones
    recalcular_redondeo_recaudaciones()


class Migration(migrations.Migration):

    dependencies = [
        ('cobranzas', '0026_recaudacion_redondeo'),
    ]

    operations = [
        migrations.RunPython(recalcular, migrations.RunPython.noop),
    ]
