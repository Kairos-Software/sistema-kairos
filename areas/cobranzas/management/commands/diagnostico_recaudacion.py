"""
diagnostico_recaudacion.py

Desarma el número "Según el sistema" que muestra la pantalla de
Recaudaciones para una entidad y una fecha, para poder ver de dónde sale
una diferencia contra el ticket de cierre de la plataforma (PagoFácil,
RapiPago o Western Union).

SOLO LECTURA: no crea, modifica ni borra nada. Se puede correr en
producción sin riesgo. No imprime datos de clientes ni observaciones.

Uso:
    python manage.py diagnostico_recaudacion pagofacil 2026-11-24
    python manage.py diagnostico_recaudacion pagofacil 2026-11-24 --ticket 248065.60
    python manage.py diagnostico_recaudacion pagofacil 2026-11-24 --detalle

--ticket  importe del ticket de la plataforma (si no se pasa, usa la
          recaudación cargada en el sistema para ese día, si existe).
--detalle lista cada boleta del canal, una por línea.
"""
from collections import defaultdict
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.utils.dateparse import parse_date

from areas.cobranzas.models import Cobro, ItemCobro, PagoCobro, RecaudacionDiaria, Servicio
from areas.cobranzas.views_recaudaciones import (
    CANAL_POR_ENTIDAD, ENTIDADES_VALIDAS, _sistema_por_canal,
)

CERO = Decimal('0')


def _m(valor) -> str:
    """Formato de plata argentino: 248065.6 -> '$248.065,60'."""
    v = Decimal(valor or 0).quantize(Decimal('0.01'))
    signo = '-' if v < 0 else ''
    entero, dec = f'{abs(v):,.2f}'.split('.')
    return f"{signo}${entero.replace(',', '.')},{dec}"


class Command(BaseCommand):
    help = ('Desarma lo que el sistema compara contra la recaudación de una entidad '
            'en una fecha (solo lectura).')

    def add_arguments(self, parser):
        parser.add_argument('entidad', help='pagofacil | rapipago | western_union')
        parser.add_argument('fecha', help='AAAA-MM-DD')
        parser.add_argument('--ticket', help='Importe del ticket de la plataforma, ej. 248065.60')
        parser.add_argument('--detalle', action='store_true',
                            help='Lista cada boleta del canal, una por línea.')

    # ──────────────────────────────────────────────────────────
    def handle(self, *args, **opts):
        entidad = opts['entidad'].strip().lower()
        if entidad not in ENTIDADES_VALIDAS:
            raise CommandError(f'Entidad inválida. Usá una de: {", ".join(sorted(ENTIDADES_VALIDAS))}')
        fecha = parse_date(opts['fecha'].strip())
        if fecha is None:
            raise CommandError('Fecha inválida. Usá AAAA-MM-DD.')

        ticket = None
        if opts.get('ticket'):
            try:
                ticket = Decimal(opts['ticket'].replace(',', '.'))
            except InvalidOperation:
                raise CommandError('--ticket inválido. Ej: 248065.60')

        canal = CANAL_POR_ENTIDAD[entidad]
        out = self.stdout.write

        out('=' * 72)
        out(f'DIAGNÓSTICO RECAUDACIÓN — {entidad} — {fecha:%d/%m/%Y}')
        out(f'(zona horaria del servidor: TIME_ZONE={settings.TIME_ZONE}, USE_TZ={settings.USE_TZ})')
        out('=' * 72)

        # ── 1. Lo mismo que muestra la pantalla ──────────────────────────
        sist = _sistema_por_canal(entidad, fecha)
        rec = RecaudacionDiaria.objects.filter(entidad=entidad, fecha=fecha).first()
        out('\n1) LO QUE MUESTRA LA PANTALLA "Según el sistema"')
        regla = ('TODO MENOS LO COBRADO CON TARJETA (Pago Electrónico)'
                 if sist['sin_tarjeta'] else 'TODOS LOS MEDIOS')
        out(f'   Regla de esta entidad:                  se declara {regla}')
        out(f'     total facturas (todos los medios):    {_m(sist["boletas_todos"])}')
        out(f'     - pagado con tarjeta (no se declara): {_m(sist["boletas_tarjeta"])}'
            f'  ({sist["cant_tarjeta"]} cobros, {sist["cant_tarjeta_parcial"]} solo en parte)')
        out(f'   Valor facial a declarar:                {_m(sist["valor_facial"])}')
        out(f'   - Comisión de la entidad:               {_m(sist["comision"])}'
            f'  ({sist["comision_cant"]} boletas × {_m(sist["comision_unit"])}'
            f'{", vigente desde " + sist["comision_desde"] if sist["comision_desde"] else ", sin comisión cargada"})')
        out(f'   = Número que se compara:                {_m(sist["boletas"])}')
        out(f'   Adicionales propios (no se comparan):   {_m(sist["adicionales_propios"])}')
        out(f'   Redondeos (no se comparan):             {_m(sist["redondeos"])}')
        out(f'   Cobros:                                 {sist["cant"]}')
        if rec:
            out(f'   Recaudación cargada ese día:            {_m(rec.monto)}'
                f'  (diferencia que ve el cajero: {_m(rec.monto - sist["boletas"])})')
            out(f'   Redondeo dentro de las facturas:        {_m(rec.redondeo)}'
                f'  (se toma solo si el sistema tiene más que lo cargado y no pasa'
                f' {_m(sist["tope_redondeo"])})')
        if ticket is not None:
            out(f'   Ticket indicado (--ticket):             {_m(ticket)}'
                f'  (diferencia: {_m(ticket - sist["boletas"])})')

        items = list(
            ItemCobro.objects
            .filter(cobro__estado=Cobro.ESTADO_CERRADO, canal=canal,
                    cobro__fecha_cierre__date=fecha)
            .select_related('servicio', 'cobro', 'cobro__turno')
            .order_by('cobro__fecha_cierre', 'orden', 'pk')
        )
        if not items:
            out('\nNo hay boletas de este canal en esa fecha. Nada más que analizar.')
            return

        cobro_ids = {i.cobro_id for i in items}

        # Pagos y total de ítems de cada cobro involucrado (todos sus ítems,
        # no solo los de este canal: un cobro puede mezclar canales).
        pagos_por_cobro = defaultdict(lambda: defaultdict(lambda: CERO))
        for p in PagoCobro.objects.filter(cobro_id__in=cobro_ids):
            pagos_por_cobro[p.cobro_id][p.metodo] += p.monto
        total_items_cobro = defaultdict(lambda: CERO)
        canales_cobro = defaultdict(set)
        for it in ItemCobro.objects.filter(cobro_id__in=cobro_ids):
            total_items_cobro[it.cobro_id] += it.monto_servicio + it.monto_adicional
            canales_cobro[it.cobro_id].add(it.canal)

        # ── 2. Según cómo pagó el cliente ────────────────────────────────
        def clase_pago(cobro_id):
            metodos = {m for m, v in pagos_por_cobro[cobro_id].items() if v > 0}
            if metodos == {PagoCobro.METODO_EFECTIVO}:
                return 'solo efectivo'
            if PagoCobro.METODO_EFECTIVO not in metodos:
                return 'sin efectivo (' + '+'.join(sorted(metodos)) + ')'
            return 'mixto (' + '+'.join(sorted(metodos)) + ')'

        por_pago = defaultdict(lambda: [CERO, 0])
        for it in items:
            k = clase_pago(it.cobro_id)
            por_pago[k][0] += it.monto_servicio
            por_pago[k][1] += 1
        out('\n2) FACTURAS DEL CANAL SEGÚN CÓMO PAGÓ EL CLIENTE')
        out('   (en PagoFácil lo pagado con tarjeta en su terminal es "Pago Electrónico"')
        out('    y no va en el ticket de efectivo; transferencias y efectivo sí van)')
        for k, (s, n) in sorted(por_pago.items(), key=lambda x: -x[1][0]):
            out(f'   {k:<45} {_m(s):>16}  ({n} boletas)')

        # ── 3. Por familia de servicio ───────────────────────────────────
        por_fam = defaultdict(lambda: [CERO, 0, set()])
        for it in items:
            fam = (it.servicio.familia or '(sin familia)').upper()
            por_fam[fam][0] += it.monto_servicio
            por_fam[fam][1] += 1
            por_fam[fam][2].add(it.servicio.tipo_precio)
        out('\n3) FACTURAS DEL CANAL POR FAMILIA DE SERVICIO')
        out('   (EX = extracciones: el efectivo se le ENTREGA al cliente. Si una')
        out('    extracción quedó cargada en este canal, el sistema la SUMA como')
        out('    si fuera una boleta cobrada. Servicios "fijo" propios —trámites,')
        out('    fotocopias, etc.— tampoco deberían estar en este canal)')
        for fam, (s, n, tipos) in sorted(por_fam.items(), key=lambda x: -x[1][0]):
            marca = '  <-- REVISAR' if fam == 'EX' or Servicio.TIPO_FIJO in tipos else ''
            out(f'   {fam:<12} {"/".join(sorted(tipos)):<11} {_m(s):>16}  ({n} boletas){marca}')

        # ── 4. Por turno ─────────────────────────────────────────────────
        por_turno = defaultdict(lambda: [CERO, 0])
        turnos = {}
        for it in items:
            t = it.cobro.turno
            clave = t.numero if t else None
            turnos[clave] = t
            por_turno[clave][0] += it.monto_servicio
            por_turno[clave][1] += 1
        out('\n4) FACTURAS DEL CANAL POR TURNO')
        out('   (la pantalla suma el DÍA calendario completo; si la plataforma cerró')
        out('    su caja en otro momento, el ticket puede no cubrir todos los turnos)')
        for num, (s, n) in sorted(por_turno.items(), key=lambda x: (x[0] is None, x[0] or 0)):
            t = turnos[num]
            if t is None:
                desc = 'sin turno'
            else:
                ap = timezone.localtime(t.fecha_apertura).strftime('%d/%m %H:%M')
                ci = (timezone.localtime(t.fecha_cierre).strftime('%d/%m %H:%M')
                      if t.fecha_cierre else 'abierto')
                desc = f'Turno #{num} ({ap} -> {ci})'
            out(f'   {desc:<45} {_m(s):>16}  ({n} boletas)')

        # ── 5. Por hora ──────────────────────────────────────────────────
        por_hora = defaultdict(lambda: [CERO, 0])
        for it in items:
            h = timezone.localtime(it.cobro.fecha_cierre).hour
            por_hora[h][0] += it.monto_servicio
            por_hora[h][1] += 1
        out('\n5) FACTURAS DEL CANAL POR HORA (hora local del servidor)')
        out('   (sirve para ver si hay cobros después de la hora en que se sacó el')
        out('    ticket de cierre de la plataforma)')
        for h in sorted(por_hora):
            s, n = por_hora[h]
            out(f'   {h:02d}:00-{h:02d}:59   {_m(s):>16}  ({n} boletas)')

        # ── 6. Señales de redondeo ───────────────────────────────────────
        # Una boleta real de luz/gas/etc. casi nunca termina justo en $X00,00.
        # Si muchas facturas por rango están "redondas", probablemente el
        # cajero cargó el redondeo en la FACTURA en vez de en el adicional.
        rango = [it for it in items if it.servicio.tipo_precio == Servicio.TIPO_RANGO]
        redondas = [it for it in rango
                    if it.monto_servicio == it.monto_servicio.to_integral_value()
                    and int(it.monto_servicio) % 50 == 0]
        out('\n6) SEÑALES DE REDONDEO')
        out(f'   Boletas por rango en el canal:                {len(rango)}')
        out(f'   ...de esas, con factura "redonda" (múltiplo de $50, sin centavos): '
            f'{len(redondas)}  suman {_m(sum((i.monto_servicio for i in redondas), CERO))}')
        out('   (si son muchas, el redondeo se está cargando en la factura: eso hace')
        out('    que el sistema muestre más que el ticket de la plataforma)')

        excedentes = []
        for cid in cobro_ids:
            pagado = sum(pagos_por_cobro[cid].values(), CERO)
            dif = pagado - total_items_cobro[cid]
            if dif > Decimal('0.009'):
                excedentes.append((cid, dif))
        out(f'   Cobros donde el pago registrado supera el total: {len(excedentes)}'
            f'  (excedente total {_m(sum((d for _, d in excedentes), CERO))})')
        out('   (ese excedente entra como efectivo de caja pero no figura ni como')
        out('    factura ni como adicional)')

        mixtos = [cid for cid in cobro_ids if len(canales_cobro[cid]) > 1]
        if mixtos:
            out(f'   Cobros que mezclan este canal con otros:        {len(mixtos)}')

        # ── 7. Cobros con fecha editada ──────────────────────────────────
        movidos = sorted({
            it.cobro_id for it in items
            if timezone.localtime(it.cobro.fecha_creacion).date()
            != timezone.localtime(it.cobro.fecha_cierre).date()
        })
        out('\n7) COBROS CUYA FECHA FUE CAMBIADA AL EDITARLOS')
        if movidos:
            out(f'   {len(movidos)} cobro(s) se crearon otro día y quedaron con fecha '
                f'{fecha:%d/%m}: #' + ', #'.join(map(str, movidos)))
        else:
            out('   Ninguno.')

        # ── 8. Detalle ───────────────────────────────────────────────────
        if opts['detalle']:
            out('\n8) DETALLE (una línea por boleta del canal)')
            out(f'   {"cobro":>7} {"hora":>5} {"turno":>5}  {"código":<12} {"fam":<6} '
                f'{"factura":>14} {"adicional":>12}  pago')
            for it in items:
                hora = timezone.localtime(it.cobro.fecha_cierre).strftime('%H:%M')
                turno = it.cobro.turno.numero if it.cobro.turno else '-'
                pagos = ', '.join(f'{m} {_m(v)}' for m, v in pagos_por_cobro[it.cobro_id].items())
                out(f'   #{it.cobro_id:>6} {hora:>5} {turno!s:>5}  {it.servicio.codigo:<12} '
                    f'{(it.servicio.familia or "-"):<6} {_m(it.monto_servicio):>14} '
                    f'{_m(it.monto_adicional):>12}  {pagos}')

        out('\nFin del diagnóstico (no se modificó nada).')
