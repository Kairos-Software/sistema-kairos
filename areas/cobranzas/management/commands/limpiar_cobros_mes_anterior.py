"""
Management command: limpiar_cobros_mes_anterior
================================================
Elimina todos los cobros cerrados del mes anterior al de ejecución.

Uso recomendado: ejecutar con un cron o Windows Task Scheduler el día 20 de cada mes.

Ejemplo cron (Linux):
    0 3 20 * * /ruta/entorno/bin/python /ruta/sistema/manage.py limpiar_cobros_mes_anterior

Ejemplo Task Scheduler (Windows): ejecutar el día 20 a las 03:00 AM:
    d:\\ruta\\entorno\\Scripts\\python.exe d:\\ruta\\sistema\\manage.py limpiar_cobros_mes_anterior

Opciones:
    --force     Ejecuta sin importar qué día del mes sea (útil para pruebas).
    --dry-run   Solo muestra cuántos registros se eliminarían, sin borrar nada.
"""

from datetime import date
from django.core.management.base import BaseCommand
from django.db import transaction

# Ajustá el import según la ubicación real de tu app
from areas.cobranzas.models import Cobro


class Command(BaseCommand):
    help = 'Elimina cobros del mes anterior. Diseñado para ejecutarse el día 20 de cada mes.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Ejecutar aunque no sea día 20.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Solo muestra cuántos registros se eliminarían, sin borrar nada.',
        )

    def handle(self, *args, **options):
        hoy = date.today()

        if hoy.day < 20 and not options['force']:
            self.stdout.write(
                self.style.WARNING(
                    f'Hoy es día {hoy.day}. La limpieza se ejecuta a partir del día 20. '
                    f'Usá --force para forzar.'
                )
            )
            return

        # Calcular mes anterior
        if hoy.month == 1:
            mes_anterior = 12
            anio_anterior = hoy.year - 1
        else:
            mes_anterior = hoy.month - 1
            anio_anterior = hoy.year

        mes_nombre = [
            '', 'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
            'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'
        ][mes_anterior]

        qs = Cobro.objects.filter(
            estado=Cobro.ESTADO_CERRADO,
            fecha_cierre__year=anio_anterior,
            fecha_cierre__month=mes_anterior,
        )
        total = qs.count()

        if options['dry_run']:
            self.stdout.write(
                self.style.SUCCESS(
                    f'[DRY RUN] Se eliminarían {total} cobro(s) de {mes_nombre} {anio_anterior}.'
                )
            )
            return

        if total == 0:
            self.stdout.write(
                self.style.WARNING(
                    f'No hay cobros de {mes_nombre} {anio_anterior} para eliminar.'
                )
            )
            return

        with transaction.atomic():
            eliminados, _ = qs.delete()

        self.stdout.write(
            self.style.SUCCESS(
                f'✓ Se eliminaron {eliminados} registro(s) de cobros de {mes_nombre} {anio_anterior}.'
            )
        )