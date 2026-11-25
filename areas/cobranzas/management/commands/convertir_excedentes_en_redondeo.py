"""
convertir_excedentes_en_redondeo.py

Antes de existir el botón "Redondear", cuando se le cobraba al cliente un
total redondeado (ej. factura 142 + adicional 100 = 242, se cobran 300) a
veces se cargaba el pago por 300 y el sistema guardaba esos 58 de más como
un "excedente" que no figuraba en ningún lado: estaban en la caja (porque el
pago en efectivo sí se registró) pero no en las ganancias.

Este comando convierte esos excedentes en lo que son: redondeo, que se suma
al adicional del cobro (100 → 158) y queda registrado en ItemCobro.monto_redondeo (58).

QUÉ NO CAMBIA (para no "romper los números"):
  - Los pagos (PagoCobro): el efectivo de caja y los cierres de turno siguen igual.
  - Las facturas (monto_servicio): las recaudaciones siguen igual.
QUÉ SÍ CAMBIA:
  - El adicional del cobro sube en el excedente → Ganancias sube en ese total.
  - Si el turno del cobro ya tiene cierre diario, su total_adicionales y
    total_redondeos guardados también suben en lo mismo, para que el historial
    de cierres coincida.

Los excedentes mayores a --maximo (default $1.000) NO se convierten: pueden
ser errores de carga (por ejemplo, haber puesto el billete que dio el cliente
en vez de lo que se cobró). Se listan para revisarlos a mano.

Uso:
    python manage.py convertir_excedentes_en_redondeo            # solo muestra (no cambia nada)
    python manage.py convertir_excedentes_en_redondeo --aplicar  # convierte
    python manage.py convertir_excedentes_en_redondeo --maximo 500

Se puede correr varias veces: un cobro ya convertido no vuelve a aparecer.
"""
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import DecimalField, OuterRef, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from areas.cobranzas.models import CierreDiario, Cobro, ItemCobro, PagoCobro
from areas.cobranzas.views_cobros import indice_item_redondeo

CERO = Decimal('0')
UMBRAL = Decimal('0.009')


def _m(valor) -> str:
    v = Decimal(valor or 0).quantize(Decimal('0.01'))
    entero, dec = f'{abs(v):,.2f}'.split('.')
    return f"{'-' if v < 0 else ''}${entero.replace(',', '.')},{dec}"


def _cobros_con_excedente():
    """Cobros cerrados sin redondeo registrado cuyo pago supera el total de ítems."""
    dec = DecimalField(max_digits=14, decimal_places=2)
    sub_items = Subquery(
        ItemCobro.objects.filter(cobro=OuterRef('pk'))
        .values('cobro').annotate(s=Sum('monto_servicio') + Sum('monto_adicional')).values('s')[:1],
        output_field=dec,
    )
    sub_pagos = Subquery(
        PagoCobro.objects.filter(cobro=OuterRef('pk'))
        .values('cobro').annotate(s=Sum('monto')).values('s')[:1],
        output_field=dec,
    )
    qs = (
        Cobro.objects
        .filter(estado=Cobro.ESTADO_CERRADO)
        .exclude(items__monto_redondeo__gt=0)
        .annotate(t_items=Coalesce(sub_items, Value(CERO), output_field=dec),
                  t_pagos=Coalesce(sub_pagos, Value(CERO), output_field=dec))
        .order_by('fecha_cierre', 'pk')
    )
    return [c for c in qs if c.t_pagos - c.t_items > UMBRAL]


class Command(BaseCommand):
    help = ('Convierte en redondeo (adicional) los excedentes de pago de cobros '
            'viejos. Sin --aplicar solo muestra lo que haría.')

    def add_arguments(self, parser):
        parser.add_argument('--aplicar', action='store_true',
                            help='Hace los cambios. Sin esto, solo muestra.')
        parser.add_argument('--maximo', default='1000',
                            help='Excedente máximo a convertir (default 1000). '
                                 'Los mayores se listan para revisar a mano.')

    def handle(self, *args, **opts):
        try:
            maximo = Decimal(str(opts['maximo']).replace(',', '.'))
        except InvalidOperation:
            raise CommandError('--maximo inválido.')
        aplicar = opts['aplicar']
        out = self.stdout.write

        candidatos = _cobros_con_excedente()
        convertir = [c for c in candidatos if c.t_pagos - c.t_items <= maximo]
        revisar = [c for c in candidatos if c.t_pagos - c.t_items > maximo]

        out('=' * 72)
        out('EXCEDENTES DE PAGO → REDONDEO ' + ('(APLICANDO)' if aplicar else '(SOLO MUESTRA, no cambia nada)'))
        out('=' * 72)
        total_conv = sum((c.t_pagos - c.t_items for c in convertir), CERO)
        out(f'Cobros a convertir: {len(convertir)}  —  total que pasa a adicional: {_m(total_conv)}')
        for c in convertir[:40]:
            fecha = timezone.localtime(c.fecha_cierre).strftime('%d/%m/%Y %H:%M') if c.fecha_cierre else '-'
            out(f'   #{c.pk:<7} {fecha}  total {_m(c.t_items):>14}  cobrado {_m(c.t_pagos):>14}'
                f'  redondeo {_m(c.t_pagos - c.t_items):>10}')
        if len(convertir) > 40:
            out(f'   ... y {len(convertir) - 40} más.')

        if revisar:
            out(f'\nNO se convierten (excedente mayor a {_m(maximo)}; revisarlos a mano): {len(revisar)}')
            for c in revisar:
                fecha = timezone.localtime(c.fecha_cierre).strftime('%d/%m/%Y %H:%M') if c.fecha_cierre else '-'
                out(f'   #{c.pk:<7} {fecha}  total {_m(c.t_items):>14}  cobrado {_m(c.t_pagos):>14}'
                    f'  de más {_m(c.t_pagos - c.t_items):>10}')

        if not aplicar:
            out('\nNo se modificó nada. Para convertir, volvé a correrlo con --aplicar.')
            return
        if not convertir:
            out('\nNada para convertir.')
            return

        with transaction.atomic():
            hechos = CERO
            for c in convertir:
                # Releer con bloqueo por si alguien lo edita en este momento.
                cobro = Cobro.objects.select_for_update().get(pk=c.pk)
                items = list(cobro.items.select_for_update().order_by('orden', 'pk'))
                t_items = sum((i.monto_servicio + i.monto_adicional for i in items), CERO)
                t_pagos = cobro.pagos.aggregate(t=Sum('monto'))['t'] or CERO
                exc = (t_pagos - t_items).quantize(Decimal('0.01'))
                if any(i.monto_redondeo for i in items) or exc <= UMBRAL or exc > maximo or not items:
                    continue
                destino = items[indice_item_redondeo([i.cantidad or 1 for i in items])]
                destino.monto_adicional += exc
                destino.monto_redondeo = exc
                destino.save(update_fields=['monto_adicional', 'monto_redondeo'])
                cierre_id = (Cobro.objects.filter(pk=cobro.pk)
                             .values_list('turno__cierre_diario_id', flat=True).first())
                if cierre_id:
                    cierre = CierreDiario.objects.select_for_update().get(pk=cierre_id)
                    cierre.total_adicionales += exc
                    cierre.total_redondeos += exc
                    cierre.save(update_fields=['total_adicionales', 'total_redondeos'])
                hechos += exc

        out(self.style.SUCCESS(f'\nListo: {_m(hechos)} pasaron a adicional como redondeo.'))
