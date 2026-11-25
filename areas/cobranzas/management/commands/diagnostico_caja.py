"""
diagnostico_caja.py

Explica, para un día, la diferencia entre los billetes contados y lo que
muestra el sistema. Arma paso a paso el "puente" entre el TOTAL GENERAL del
Historial de cobros (filtrado por PagoFácil + RapiPago, que NO es el
efectivo de la caja) y el EFECTIVO ESPERADO en el cajón.

SOLO LECTURA: no crea, modifica ni borra nada. Se puede correr en
producción sin riesgo. No imprime datos de clientes ni observaciones.

Uso:
    python manage.py diagnostico_caja 2026-11-24
    python manage.py diagnostico_caja 2026-11-24 --contado 695400
    python manage.py diagnostico_caja 2026-11-24 --contado 695400 --detalle

--contado  lo que dio el contador de billetes (si se pasa, calcula la diferencia).
--detalle  lista cada cobro del día, uno por línea.
"""
from collections import defaultdict
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.utils.dateparse import parse_date

from areas.cobranzas.models import Cobro, ItemCobro, PagoCobro, Turno

CERO = Decimal('0')
CANALES_HISTORIAL = {ItemCobro.CANAL_PAGOFACIL, ItemCobro.CANAL_RAPIPAGO}


def _m(valor) -> str:
    """Formato de plata argentino: 248065.6 -> '$248.065,60'."""
    v = Decimal(valor or 0).quantize(Decimal('0.01'))
    signo = '-' if v < 0 else ''
    entero, dec = f'{abs(v):,.2f}'.split('.')
    return f"{signo}${entero.replace(',', '.')},{dec}"


class Command(BaseCommand):
    help = ('Explica la diferencia entre el efectivo contado y el sistema para un día '
            '(solo lectura).')

    def add_arguments(self, parser):
        parser.add_argument('fecha', help='AAAA-MM-DD')
        parser.add_argument('--contado', help='Lo que dio el contador de billetes, ej. 695400')
        parser.add_argument('--detalle', action='store_true',
                            help='Lista cada cobro del día, uno por línea.')

    def handle(self, *args, **opts):
        fecha = parse_date(opts['fecha'].strip())
        if fecha is None:
            raise CommandError('Fecha inválida. Usá AAAA-MM-DD.')
        contado = None
        if opts.get('contado'):
            txt = opts['contado'].replace('$', '').replace(' ', '')
            if ',' in txt:                      # 695.400,50 -> 695400.50
                txt = txt.replace('.', '').replace(',', '.')
            elif '.' in txt and len(txt.rsplit('.', 1)[1]) == 3:   # 695.400 -> 695400
                txt = txt.replace('.', '')
            try:
                contado = Decimal(txt)
            except InvalidOperation:
                raise CommandError('--contado inválido. Ej: 695400')

        out = self.stdout.write
        out('=' * 74)
        out(f'DIAGNÓSTICO DE CAJA — {fecha:%d/%m/%Y}')
        out(f'(zona horaria del servidor: TIME_ZONE={settings.TIME_ZONE}, USE_TZ={settings.USE_TZ})')
        out('=' * 74)

        cobros = list(
            Cobro.objects
            .filter(estado=Cobro.ESTADO_CERRADO, fecha_cierre__date=fecha)
            .select_related('turno')
            .prefetch_related('items__servicio', 'pagos')
            .order_by('fecha_cierre', 'pk')
        )

        # Datos por cobro
        info = []
        for c in cobros:
            items = list(c.items.all())
            pagos = defaultdict(lambda: CERO)
            for p in c.pagos.all():
                pagos[p.metodo] += p.monto
            t_items = sum((i.monto_servicio + i.monto_adicional for i in items), CERO)
            t_pagos = sum(pagos.values(), CERO)
            info.append({
                'c': c, 'items': items, 'pagos': pagos,
                'canales': {i.canal for i in items},
                't_items': t_items, 't_pagos': t_pagos,
                'efectivo': pagos.get(PagoCobro.METODO_EFECTIVO, CERO),
                'facturas': sum((i.monto_servicio for i in items), CERO),
                'adicionales': sum((i.monto_adicional for i in items), CERO),
                'ext': sum((i.monto_servicio for i in items
                            if (i.servicio.familia or '').upper() == 'EX'), CERO),
            })

        # ── 1. Lo que muestra el Historial de cobros ─────────────────────
        hist = [x for x in info if x['canales'] & CANALES_HISTORIAL]
        otros_canales = [x for x in info if not (x['canales'] & CANALES_HISTORIAL)]
        H = sum((x['t_items'] for x in hist), CERO)
        out('\n1) HISTORIAL DE COBROS filtrado por PagoFácil + RapiPago')
        out(f'   Cobros:              {len(hist)}')
        out(f'   Total facturas:      {_m(sum((x["facturas"] for x in hist), CERO))}')
        out(f'   Total adicionales:   {_m(sum((x["adicionales"] for x in hist), CERO))}')
        out(f'   TOTAL GENERAL:       {_m(H)}   <- este número NO es el efectivo del cajón')

        # ── 2. Puente: del Total general al efectivo de esos cobros ──────
        P = sum((x['t_pagos'] for x in hist), CERO)
        E = sum((x['efectivo'] for x in hist), CERO)
        O = P - E
        X = P - H
        out('\n2) DEL TOTAL GENERAL AL EFECTIVO COBRADO (esos mismos cobros)')
        out(f'   Total general                                   {_m(H):>16}')
        out(f'   + pagado de más / - de menos que el total       {_m(X):>16}'
            '   (pagos registrados - facturas+adicionales)')
        out(f'   - cobrado con tarjeta/transferencia/QR          {_m(-O):>16}'
            '   (no entra al cajón)')
        out(f'   = efectivo cobrado en esos cobros               {_m(E):>16}')
        if O:
            por_metodo = defaultdict(lambda: CERO)
            for x in hist:
                for m, v in x['pagos'].items():
                    if m != PagoCobro.METODO_EFECTIVO:
                        por_metodo[m] += v
            nombres = dict(PagoCobro.METODOS)
            out('     detalle otros medios: ' + ', '.join(
                f'{nombres.get(m, m)} {_m(v)}' for m, v in sorted(por_metodo.items())))

        # ── 3. Turnos del día ────────────────────────────────────────────
        turnos = {x['c'].turno_id: x['c'].turno for x in info if x['c'].turno_id}
        for t in Turno.objects.filter(fecha_apertura__date=fecha):
            turnos.setdefault(t.pk, t)
        out('\n3) TURNOS DEL DÍA')
        F = I = R = EXT = ESP = CERO
        for t in sorted(turnos.values(), key=lambda t: t.numero):
            ap = timezone.localtime(t.fecha_apertura).strftime('%d/%m %H:%M')
            ci = timezone.localtime(t.fecha_cierre).strftime('%d/%m %H:%M') if t.fecha_cierre else 'abierto'
            esp = t.efectivo_esperado()
            out(f'   Turno #{t.numero} ({ap} -> {ci})')
            out(f'     fondo inicial {_m(t.monto_inicial)} | efectivo cobrado {_m(t.total_efectivo())}'
                f' | ingresos {_m(t.total_ingresos())} | retiros {_m(t.total_retiros())}'
                f' | extracciones EX {_m(t.total_extracciones())}')
            linea = f'     efectivo esperado {_m(esp)}'
            if t.efectivo_declarado is not None:
                linea += (f' | declarado al cerrar {_m(t.efectivo_declarado)}'
                          f' | diferencia registrada {_m(t.diferencia or CERO)}')
            out(linea)
            F += t.monto_inicial
            I += t.total_ingresos()
            R += t.total_retiros()
            EXT += t.total_extracciones()
            ESP += esp
            fuera = (Cobro.objects.filter(turno=t, estado=Cobro.ESTADO_CERRADO)
                     .exclude(fecha_cierre__date=fecha).count())
            if fuera:
                out(f'     ATENCIÓN: este turno tiene {fuera} cobro(s) con fecha de otro día.')
        if not turnos:
            out('   No hay turnos para ese día.')

        # ── 4. Puente completo hasta el efectivo esperado ────────────────
        E2 = sum((x['efectivo'] for x in otros_canales), CERO)
        sin_turno = sum((x['efectivo'] for x in info if not x['c'].turno_id), CERO)
        calc = F + E + E2 + I - R - EXT - sin_turno
        out('\n4) DEL EFECTIVO COBRADO AL EFECTIVO QUE TIENE QUE HABER EN EL CAJÓN')
        out(f'   efectivo cobrado PagoFácil + RapiPago           {_m(E):>16}')
        out(f'   + efectivo de cobros de OTROS canales           {_m(E2):>16}'
            f'   ({len(otros_canales)} cobros: Western Union / Otro; el filtro del historial los oculta)')
        out(f'   + fondo inicial de los turnos                   {_m(F):>16}')
        out(f'   + ingresos de caja                              {_m(I):>16}')
        out(f'   - retiros de caja                               {_m(-R):>16}')
        out(f'   - extracciones (EX: efectivo entregado)         {_m(-EXT):>16}')
        if sin_turno:
            out(f'   - efectivo de cobros sin turno                  {_m(-sin_turno):>16}')
        out(f'   = EFECTIVO ESPERADO                             {_m(calc):>16}')
        if turnos and abs(calc - ESP) > Decimal('0.009'):
            out(f'   (la suma de "efectivo esperado" de cada turno da {_m(ESP)}: la diferencia es')
            out('    porque algún turno tiene cobros de otro día; usá ese número)')
        if contado is not None:
            dif = contado - calc
            out(f'\n   Contado (--contado)                             {_m(contado):>16}')
            out(f'   Diferencia contado - esperado                   {_m(dif):>16}'
                f'   ({"SOBRA" if dif > 0 else "FALTA" if dif < 0 else "OK"})')
            out(f'   Contado - Total general del historial           {_m(contado - H):>16}'
                '   (la comparación que NO sirve)')

        # ── 5. Señales ───────────────────────────────────────────────────
        out('\n5) COSAS PARA REVISAR')
        exced = [x for x in info if abs(x['t_pagos'] - x['t_items']) > Decimal('0.009')]
        out(f'   Cobros donde lo pagado != facturas+adicionales: {len(exced)}')
        for x in exced:
            out(f'     #{x["c"].pk}: total {_m(x["t_items"])}, pagado {_m(x["t_pagos"])}'
                f' ({_m(x["t_pagos"] - x["t_items"])})')
        for x in otros_canales:
            canales = '+'.join(sorted(x['canales']))
            out(f'   Cobro #{x["c"].pk} de canal {canales}: total {_m(x["t_items"])},'
                f' efectivo {_m(x["efectivo"])}')
        ext_items = [(x['c'].pk, i) for x in info for i in x['items']
                     if (i.servicio.familia or '').upper() == 'EX']
        for cid, i in ext_items:
            out(f'   Extracción en cobro #{cid}: {i.servicio.codigo} entrega {_m(i.monto_servicio)}'
                f' (canal {i.canal})')
        redondas = [i for x in hist for i in x['items']
                    if i.servicio.tipo_precio == i.servicio.TIPO_RANGO
                    and (i.servicio.familia or '').upper() != 'EX'
                    and i.monto_servicio == i.monto_servicio.to_integral_value()
                    and int(i.monto_servicio) % 50 == 0 and not i.monto_redondeo]
        out(f'   Facturas "redondas" (múltiplo de $50, sin centavos): {len(redondas)}')
        out('     Si se redondeó al cobrar y el redondeo quedó DENTRO de la factura, ese')
        out('     redondeo YA está sumado en el total general y en el efectivo esperado:')
        out('     no genera plata de más en el cajón. Sí hace que el sistema tenga más')
        out('     que el ticket de la plataforma (se corrige en Recaudaciones -> "Ver las')
        out('     boletas de ese día").')

        # ── 6. Detalle ───────────────────────────────────────────────────
        if opts['detalle']:
            nombres = dict(PagoCobro.METODOS)
            out('\n6) DETALLE (un cobro por línea)')
            for x in info:
                c = x['c']
                hora = timezone.localtime(c.fecha_cierre).strftime('%H:%M')
                turno = c.turno.numero if c.turno else '-'
                cods = ', '.join(f'{i.servicio.codigo}({i.canal}) {_m(i.monto_servicio)}'
                                 f'+{_m(i.monto_adicional)}' for i in x['items'])
                pagos = ', '.join(f'{nombres.get(m, m)} {_m(v)}' for m, v in x['pagos'].items())
                out(f'   #{c.pk} {hora} T{turno}: {cods} | pagos: {pagos}')

        out('\nFin del diagnóstico (no se modificó nada).')
