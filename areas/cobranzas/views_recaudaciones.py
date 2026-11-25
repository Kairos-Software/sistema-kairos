"""
views_recaudaciones.py
Vistas para el módulo de Recaudaciones Diarias (PagoFácil / RapiPago).

Lógica de negocio:
  - Cada día se registra UNA recaudación por entidad (unique_together).
  - Si ya existe para esa entidad+fecha se puede modificar (PUT-like via POST con pk).
  - El balance pendiente de depositar se calcula en tiempo real:
      pendiente = SUM(RecaudacionDiaria.monto) - SUM(DepositoBancario.monto)
    (filtrado por entidad en ambos lados)
"""
import json
from decimal import Decimal, InvalidOperation

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Sum, Q
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views import View

from decimal import Decimal

from .models import (
    RecaudacionDiaria, DepositoBancario, AjusteSaldoFavor, ItemCobro, Cobro, PagoCobro,
    ComisionEntidad, CierreDiario,
)


# Entidades válidas de recaudación/depósito (mismas 3 en todo el módulo).
ENTIDADES_VALIDAS = {e for e, _ in RecaudacionDiaria.ENTIDADES}

# Canal de ItemCobro que corresponde a cada entidad de recaudación.
CANAL_POR_ENTIDAD = {
    RecaudacionDiaria.ENTIDAD_PAGOFACIL:     ItemCobro.CANAL_PAGOFACIL,
    RecaudacionDiaria.ENTIDAD_RAPIPAGO:      ItemCobro.CANAL_RAPIPAGO,
    RecaudacionDiaria.ENTIDAD_WESTERN_UNION: ItemCobro.CANAL_WESTERN_UNION,
}


# Qué se declara en la recaudación de cada entidad (regla del negocio):
#   - PagoFácil: SOLO lo cobrado en efectivo. Su ticket de cierre separa el
#     efectivo de lo cobrado con otros medios, y solo el efectivo se recauda.
#   - RapiPago: TODO junto (efectivo + débito + transferencia + QR), sin separar.
#   - Western Union: igual que RapiPago por ahora (todavía no hay una regla propia).
ENTIDADES_SOLO_EFECTIVO = {RecaudacionDiaria.ENTIDAD_PAGOFACIL}

CENT = Decimal('0.01')

# Una diferencia mayor entre lo cargado y la boleta real ya no parece un
# redondeo sino un error de carga (o un cobro que la plataforma no tomó).
MAX_REDONDEO_FACTURA = Decimal('1000')


def _pesos(valor) -> str:
    """Formato argentino para mensajes: Decimal('18246.86') -> '$18.246,86'."""
    v = Decimal(valor or 0).quantize(CENT)
    entero, dec = f'{abs(v):,.2f}'.split('.')
    return f"{'-' if v < 0 else ''}${entero.replace(',', '.')},{dec}"


def _sistema_por_canal(entidad: str, fecha) -> dict:
    """
    Lo que el SISTEMA registró en cobros por el canal de esa entidad, para
    una fecha dada (según fecha_cierre del cobro). Sirve para contrastar
    contra la recaudación que el cajero carga a mano leyéndola de la
    plataforma: si no coinciden, hay algo mal cargado de un lado o del otro.

    Las facturas (monto_servicio, plata de terceros) se separan según cómo
    pagó el cliente cada cobro:
      - 'boletas_efectivo' : cobros pagados solo en efectivo.
      - 'boletas_otros'    : cobros pagados sin nada de efectivo.
      - 'boletas_mixto'    : cobros que combinan efectivo con otro medio. El
        sistema no sabe qué boleta se pagó con qué, así que estima la parte en
        efectivo en proporción a lo pagado en efectivo ('mixto_efectivo_estimado').

    'valor_facial' es la suma de facturas que corresponde declarar:
      - PagoFácil  → boletas_efectivo + mixto_efectivo_estimado (solo efectivo)
      - RapiPago/WU → boletas_todos (todos los medios)
    'comision' = comisión por boleta de la entidad (ComisionEntidad vigente en
    esa fecha) × cantidad de boletas declaradas. Ej. RapiPago: 4 × $55 = $220.
    'boletas' = valor_facial − comision → el número que se compara con lo que
    carga el cajero (en RapiPago, la columna "Débito" de su resumen).
    'adicionales' = SUM(monto_adicional) de todos los medios (ganancia, no se
    declara), que incluye 'redondeos'; 'adicionales_propios' = sin redondeos.
    'tope_redondeo' = hasta cuánto de diferencia a favor del sistema se
    puede tomar como redondeo cargado dentro de las facturas: $1.000 por cada
    boleta declarada con factura "redonda" (sin centavos, múltiplo de $50),
    que son las únicas que pueden tener un redondeo adentro.
    """
    solo_efectivo = entidad in ENTIDADES_SOLO_EFECTIVO
    com = ComisionEntidad.vigente(entidad, fecha)
    comision_unit = com.monto_por_boleta if com else Decimal('0')
    vacio = {
        'boletas': Decimal('0'), 'valor_facial': Decimal('0'), 'boletas_todos': Decimal('0'),
        'boletas_efectivo': Decimal('0'), 'boletas_otros': Decimal('0'),
        'boletas_mixto': Decimal('0'), 'mixto_efectivo_estimado': Decimal('0'),
        'comision': Decimal('0'), 'comision_unit': comision_unit, 'comision_cant': 0,
        'comision_desde': str(com.vigente_desde) if com else None,
        'adicionales': Decimal('0'), 'redondeos': Decimal('0'),
        'adicionales_propios': Decimal('0'), 'total': Decimal('0'),
        'cant': 0, 'cant_otros': 0, 'cant_mixto': 0,
        'cant_redondas': 0, 'tope_redondeo': Decimal('0'),
        'solo_efectivo': solo_efectivo,
    }
    canal = CANAL_POR_ENTIDAD.get(entidad)
    if canal is None or fecha is None:
        return vacio

    items = list(
        ItemCobro.objects
        .filter(cobro__estado=Cobro.ESTADO_CERRADO, canal=canal,
                cobro__fecha_cierre__date=fecha)
        .values('cobro_id', 'monto_servicio', 'monto_adicional', 'monto_redondeo', 'cantidad')
    )
    if not items:
        return vacio

    boletas_cobro = {}
    unidades_cobro = {}   # boletas (unidades) de este canal por cobro, para la comisión
    redondas_cobro = {}   # boletas con factura "redonda" (pueden tener un redondeo adentro)
    adicionales = Decimal('0')
    redondeos = Decimal('0')
    for it in items:
        cid = it['cobro_id']
        boletas_cobro[cid] = boletas_cobro.get(cid, Decimal('0')) + it['monto_servicio']
        unidades_cobro[cid] = unidades_cobro.get(cid, 0) + (it['cantidad'] or 1)
        fac = it['monto_servicio']
        if fac > 0 and fac == fac.to_integral_value() and int(fac) % 50 == 0:
            redondas_cobro[cid] = redondas_cobro.get(cid, 0) + 1
        adicionales += it['monto_adicional']
        redondeos += it['monto_redondeo']

    # Lo pagado por cada cobro (todo el cobro, aunque mezcle canales).
    pagado = {}
    efectivo = {}
    for p in (PagoCobro.objects.filter(cobro_id__in=boletas_cobro.keys())
              .values('cobro_id', 'metodo').annotate(s=Sum('monto'))):
        pagado[p['cobro_id']] = pagado.get(p['cobro_id'], Decimal('0')) + p['s']
        if p['metodo'] == PagoCobro.METODO_EFECTIVO:
            efectivo[p['cobro_id']] = efectivo.get(p['cobro_id'], Decimal('0')) + p['s']

    r = dict(vacio)
    unidades_declaradas = 0
    redondas_declaradas = 0
    for cid, bol in boletas_cobro.items():
        tot = pagado.get(cid, Decimal('0'))
        efe = efectivo.get(cid, Decimal('0'))
        r['boletas_todos'] += bol
        if efe <= 0 or tot <= 0:
            r['boletas_otros'] += bol
            r['cant_otros'] += 1
            if not solo_efectivo:
                unidades_declaradas += unidades_cobro[cid]
                redondas_declaradas += redondas_cobro.get(cid, 0)
        elif efe >= tot:
            r['boletas_efectivo'] += bol
            unidades_declaradas += unidades_cobro[cid]
            redondas_declaradas += redondas_cobro.get(cid, 0)
        else:
            r['boletas_mixto'] += bol
            r['mixto_efectivo_estimado'] += (bol * efe / tot).quantize(CENT)
            r['cant_mixto'] += 1
            unidades_declaradas += unidades_cobro[cid]
            redondas_declaradas += redondas_cobro.get(cid, 0)

    r['adicionales'] = adicionales
    r['redondeos'] = redondeos
    r['adicionales_propios'] = adicionales - redondeos
    r['total'] = r['boletas_todos'] + adicionales
    r['cant'] = len(boletas_cobro)
    r['valor_facial'] = (r['boletas_efectivo'] + r['mixto_efectivo_estimado']
                         if solo_efectivo else r['boletas_todos'])
    r['comision_cant'] = unidades_declaradas
    r['comision'] = (comision_unit * unidades_declaradas).quantize(CENT)
    r['boletas'] = r['valor_facial'] - r['comision']
    r['cant_redondas'] = redondas_declaradas
    r['tope_redondeo'] = MAX_REDONDEO_FACTURA * redondas_declaradas
    return r


def redondeo_detectado(sist: dict, monto) -> Decimal:
    """
    Redondeo que quedó cargado DENTRO de las facturas, deducido del ticket:
    si el sistema tiene un poco más que lo que se declara (el ticket de la
    plataforma), esa diferencia es lo que se cobró de más al redondear, y es
    ganancia. Ej. PagoFácil 24/11/2026: sistema $248.200 en efectivo, ticket
    $248.065,60 -> $134,40 de redondeo.

    Solo se toma como redondeo si la diferencia es a favor del sistema y no
    pasa el tope (ver 'tope_redondeo'). Si el ticket tiene MÁS que el sistema,
    o la diferencia es demasiado grande, no es redondeo: es algo para revisar.
    """
    if monto is None:
        return Decimal('0')
    dif = (sist['boletas'] - Decimal(monto)).quantize(CENT)
    if dif > 0 and dif <= sist['tope_redondeo']:
        return dif
    return Decimal('0')


def recalcular_redondeo_recaudaciones(fechas=None) -> int:
    """
    Vuelve a calcular RecaudacionDiaria.redondeo (todas, o las de esas fechas).
    Se llama al registrar una recaudación y cada vez que cambian los cobros de
    un día que ya tiene recaudación, para que el redondeo nunca se cuente dos
    veces (si después se corrigen las boletas una por una, la diferencia con
    el ticket baja y este redondeo baja en lo mismo). Devuelve cuántas cambió.
    """
    qs = RecaudacionDiaria.objects.all()
    if fechas is not None:
        fechas = {f for f in fechas if f}
        if not fechas:
            return 0
        qs = qs.filter(fecha__in=fechas)
    cambiadas = 0
    for rec in qs:
        nuevo = redondeo_detectado(_sistema_por_canal(rec.entidad, rec.fecha), rec.monto)
        if nuevo != rec.redondeo:
            RecaudacionDiaria.objects.filter(pk=rec.pk).update(redondeo=nuevo)
            cambiadas += 1
    return cambiadas


def _sistema_json(s: dict) -> dict:
    """Versión serializable (Decimal → float) de _sistema_por_canal()."""
    return {k: (float(v) if isinstance(v, Decimal) else v) for k, v in s.items()}


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────

def _ultima_diferencia(entidad: str):
    """
    Saldo a favor/en contra vigente para esa entidad: la diferencia del
    último depósito, descontando cualquier uso posterior del saldo a favor
    (AjusteSaldoFavor — ej. cargas de SUBE hechas directo con el saldo de
    la plataforma, sin pasar por un depósito real). None si todavía no
    hubo ningún depósito para esta entidad.
    """
    ultimo = (
        DepositoBancario.objects
        .filter(entidad=entidad)
        .order_by('-fecha', '-fecha_registro')
        .first()
    )
    if ultimo is None:
        return None

    usos = (
        AjusteSaldoFavor.objects
        .filter(entidad=entidad)
        .filter(
            Q(fecha__gt=ultimo.fecha) |
            Q(fecha=ultimo.fecha, fecha_registro__gt=ultimo.fecha_registro)
        )
        .aggregate(t=Sum('monto'))['t'] or Decimal('0')
    )
    return (ultimo.diferencia or Decimal('0')) - usos


def _recaudado_pendiente(entidad: str) -> Decimal:
    """
    Suma exacta de RecaudacionDiaria todavía no cubierta por ningún depósito
    (cubierta_por__isnull=True). Reemplaza la vieja aproximación por rango de
    fechas: cada recaudación queda marcada por el depósito que la cubrió al
    registrarse (ver RegistrarDepositoAjax en views_depositos.py), así que
    esto es exacto sin importar si depósito y recaudación caen el mismo día.
    """
    return (
        RecaudacionDiaria.objects
        .filter(entidad=entidad, cubierta_por__isnull=True)
        .aggregate(t=Sum('monto'))['t'] or Decimal('0')
    )


def _totales_por_entidad(entidad: str) -> dict:
    """
    Devuelve recaudado/depositado (totales informativos, todo el historial)
    y pendiente (el número accionable) para una entidad.

    'pendiente' = Recaudado pendiente (exacto, día por día) − Saldo anterior
    (diferencia del último depósito). Es la misma fórmula que usa
    FrmDeposito en el Excel de referencia para "Neto a depositar" — ya no es
    recaudado_total − depositado_total acumulado, porque con selección
    exacta de días esas dos cuentas pueden divergir (ej. si un depósito no
    cubre absolutamente todo lo pendiente).
    """
    recaudado  = (
        RecaudacionDiaria.objects
        .filter(entidad=entidad)
        .aggregate(t=Sum('monto'))['t'] or Decimal('0')
    )
    depositado = (
        DepositoBancario.objects
        .filter(entidad=entidad)
        .aggregate(t=Sum('monto'))['t'] or Decimal('0')
    )
    recaudado_pendiente = _recaudado_pendiente(entidad)
    saldo_anterior = _ultima_diferencia(entidad) or Decimal('0')
    pendiente = recaudado_pendiente - saldo_anterior
    return {
        # 'recaudado' es un acumulado de TODO el historial (crece para
        # siempre, incluso después de depositado) — no se muestra en
        # pantalla porque no aporta información accionable, ver
        # 'recaudado_pendiente' para el número que sí importa día a día.
        'recaudado':            recaudado,
        'recaudado_pendiente':  recaudado_pendiente,
        'depositado':           depositado,
        'pendiente':            pendiente,
        # 'pendiente' se mantiene con signo (lo usa el cálculo de 'diferencia'
        # en views_depositos.py). Para mostrar en pantalla conviene separarlo
        # en dos valores siempre positivos: lo que falta depositar, o —si se
        # depositó de más— el saldo a favor.
        'pendiente_mostrar': max(pendiente, Decimal('0')),
        'a_favor':           max(-pendiente, Decimal('0')),
    }


def _recaudacion_as_dict(r: RecaudacionDiaria) -> dict:
    try:
        fecha_display = r.fecha.strftime('%d/%m/%Y')
    except AttributeError:
        from datetime import datetime
        fecha_display = datetime.strptime(str(r.fecha), '%Y-%m-%d').strftime('%d/%m/%Y')

    return {
        'id':            r.pk,
        'entidad':       r.entidad,
        'entidad_label': r.get_entidad_display(),
        'fecha':         fecha_display,
        'fecha_iso':     str(r.fecha),
        'monto':         float(r.monto),
        'observaciones': r.observaciones or '',
        'cubierta_por_id': r.cubierta_por_id,
        'registrado_por': (
            r.registrado_por.get_full_name() or r.registrado_por.username
            if r.registrado_por else '—'
        ),
    }


# ─────────────────────────────────────────────────────────────
# VISTA PRINCIPAL
# ─────────────────────────────────────────────────────────────

class RecaudacionesView(LoginRequiredMixin, View):
    def get(self, request):
        entidad = request.GET.get('entidad', RecaudacionDiaria.ENTIDAD_PAGOFACIL)
        if entidad not in ENTIDADES_VALIDAS:
            entidad = RecaudacionDiaria.ENTIDAD_PAGOFACIL

        PF = RecaudacionDiaria.ENTIDAD_PAGOFACIL
        RP = RecaudacionDiaria.ENTIDAD_RAPIPAGO
        WU = RecaudacionDiaria.ENTIDAD_WESTERN_UNION

        # Totales para los botones de entidad
        tot_pf = _totales_por_entidad(PF)
        tot_rp = _totales_por_entidad(RP)
        tot_wu = _totales_por_entidad(WU)

        # Cuenta solo días PENDIENTES (no cubiertos por un depósito) — una vez
        # depositada, esa recaudación ya cumplió su función y no aporta nada
        # seguir contándola acá; para verla queda el historial completo.
        def _cant_pendientes(ent):
            return RecaudacionDiaria.objects.filter(
                entidad=ent, cubierta_por__isnull=True).count()
        cant_pf = _cant_pendientes(PF)
        cant_rp = _cant_pendientes(RP)
        cant_wu = _cant_pendientes(WU)

        # Recaudaciones pendientes de la entidad activa — las ya cubiertas por
        # un depósito "desaparecen" de este listado (son historia vieja, se
        # consultan en el historial completo, no acá donde se opera el día a día).
        ultimas = (
            RecaudacionDiaria.objects
            .filter(entidad=entidad, cubierta_por__isnull=True)
            .select_related('registrado_por')[:15]
        )

        # ¿Ya existe recaudación hoy para esta entidad? (para precargar el form)
        hoy = timezone.localdate()
        recaudacion_hoy = RecaudacionDiaria.objects.filter(entidad=entidad, fecha=hoy).first()

        tot_por_entidad = {PF: tot_pf, RP: tot_rp, WU: tot_wu}
        tot_activo = tot_por_entidad[entidad]

        # CAMBIO: los totales se pasan como JSON (via json_script) en vez de
        # interpolar {{ valor|floatformat:2 }} directo en un <script>. Con
        # LANGUAGE_CODE=es-es, floatformat usa coma decimal ("50000,00"),
        # lo que generaba un literal numérico JS inválido y rompía TODO el
        # script de la página (incluido el botón "Registrar recaudación").
        totales_json = {
            PF: {k: float(v) for k, v in tot_pf.items()},
            RP: {k: float(v) for k, v in tot_rp.items()},
            WU: {k: float(v) for k, v in tot_wu.items()},
        }

        # Contraste sistema vs. carga manual, para la fecha del formulario
        # (por defecto hoy, o la de la recaudación que ya exista para hoy).
        fecha_form = recaudacion_hoy.fecha if recaudacion_hoy else hoy

        sistema_json = {
            'fecha':  str(fecha_form),
            PF: _sistema_json(_sistema_por_canal(PF, fecha_form)),
            RP: _sistema_json(_sistema_por_canal(RP, fecha_form)),
            WU: _sistema_json(_sistema_por_canal(WU, fecha_form)),
        }

        return render(request, 'cobranzas/recaudaciones.html', {
            'entidad':          entidad,
            'entidad_label':    dict(RecaudacionDiaria.ENTIDADES).get(entidad, entidad),
            'ultimas':          ultimas,
            'tot_pf':           tot_pf,
            'tot_rp':           tot_rp,
            'tot_wu':           tot_wu,
            'tot_activo':       tot_activo,
            'totales_json':     totales_json,
            'sistema_json':     sistema_json,
            'cant_pf':          cant_pf,
            'cant_rp':          cant_rp,
            'cant_wu':          cant_wu,
            'recaudacion_hoy':  recaudacion_hoy,
            'solo_efectivo':    entidad in ENTIDADES_SOLO_EFECTIVO,
            'comision_actual':  ComisionEntidad.vigente(entidad, hoy),
            'comisiones_hist':  ComisionEntidad.objects.filter(entidad=entidad)
                                .select_related('registrado_por')[:6],
            'ENTIDAD_PF':       PF,
            'ENTIDAD_RP':       RP,
            'ENTIDAD_WU':       WU,
            'hoy':              hoy,
        })


# ─────────────────────────────────────────────────────────────
# AJAX: registrar / modificar recaudación
# ─────────────────────────────────────────────────────────────

class RegistrarRecaudacionAjax(LoginRequiredMixin, View):
    """
    POST con JSON:
      { entidad, fecha, monto, observaciones, id (opcional), modo (opcional) }

    Comportamiento:
      - Con 'id' → modo edición explícita: actualiza esa RecaudacionDiaria
        puntual por PK (puede incluso cambiarle la fecha). No aplica si ya
        fue cubierta por un depósito.
      - Sin 'id' → comportamiento de siempre, upsert por (entidad, fecha):
        si ya existe una recaudación para ese día se actualiza (sumando o
        reemplazando según 'modo'), si no existe se crea.

    Parámetro opcional 'modo' (solo aplica al upsert sin 'id'):
      - 'reemplazar' (default): el monto enviado reemplaza al existente.
      - 'sumar': el monto se suma al existente.
    """
    def post(self, request):
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        entidad = data.get('entidad', '').strip()
        if entidad not in ENTIDADES_VALIDAS:
            return JsonResponse({'error': 'Entidad inválida.'}, status=400)

        fecha_raw = data.get('fecha', '').strip()
        if not fecha_raw:
            return JsonResponse({'error': 'La fecha es obligatoria.'}, status=400)
        fecha = parse_date(fecha_raw)
        if fecha is None:
            return JsonResponse({'error': 'Fecha inválida. Usá el formato AAAA-MM-DD.'}, status=400)
        if fecha > timezone.localdate():
            return JsonResponse({'error': 'La fecha no puede ser futura.'}, status=400)

        try:
            monto = Decimal(str(data.get('monto', 0)))
            if monto <= 0:
                raise ValueError
        except (ValueError, InvalidOperation):
            return JsonResponse({'error': 'El monto debe ser mayor a cero.'}, status=400)

        observaciones = data.get('observaciones', '').strip()
        id_editar     = data.get('id')

        with transaction.atomic():
            if id_editar:
                # ── Edición explícita de un registro puntual ──
                rec = RecaudacionDiaria.objects.filter(pk=id_editar, entidad=entidad).first()
                if rec is None:
                    return JsonResponse({'error': 'No se encontró la recaudación a editar.'}, status=404)
                if rec.cubierta_por_id:
                    return JsonResponse({
                        'error': f'Esta recaudación ya fue cubierta por el depósito '
                                 f'#{rec.cubierta_por_id}, no se puede editar.'
                    }, status=400)
                conflicto = (
                    RecaudacionDiaria.objects
                    .filter(entidad=entidad, fecha=fecha)
                    .exclude(pk=rec.pk)
                    .first()
                )
                if conflicto:
                    return JsonResponse({
                        'error': f'Ya existe otra recaudación (#{conflicto.pk}) para esa fecha.'
                    }, status=400)
                rec.fecha = fecha
                rec.monto = monto
                rec.observaciones = observaciones
                rec.registrado_por = request.user
                rec.save()
                es_nueva = False
            else:
                # ── Upsert por (entidad, fecha), comportamiento de siempre ──
                modo = data.get('modo', 'reemplazar')  # 'reemplazar' | 'sumar'
                existente = RecaudacionDiaria.objects.filter(entidad=entidad, fecha=fecha).first()

                if existente and existente.cubierta_por_id:
                    return JsonResponse({
                        'error': f'Esta recaudación ya fue cubierta por el depósito '
                                 f'#{existente.cubierta_por_id}, no se puede modificar.'
                    }, status=400)

                if existente:
                    if modo == 'sumar':
                        existente.monto += monto
                    else:
                        existente.monto = monto
                    if observaciones:
                        existente.observaciones = observaciones
                    existente.registrado_por = request.user
                    existente.save()
                    rec = existente
                else:
                    rec = RecaudacionDiaria.objects.create(
                        entidad=entidad,
                        fecha=fecha,
                        monto=monto,
                        observaciones=observaciones,
                        registrado_por=request.user,
                    )
                es_nueva = not bool(existente)

        totales = _totales_por_entidad(entidad)
        sist = _sistema_por_canal(entidad, rec.fecha)
        rec.redondeo = redondeo_detectado(sist, rec.monto)
        rec.save(update_fields=['redondeo'])

        return JsonResponse({
            'success':              True,
            'recaudacion':          _recaudacion_as_dict(rec),
            'redondeo':             float(rec.redondeo),
            'es_nueva':             es_nueva,
            'total_recaudado':      float(totales['recaudado']),
            'recaudado_pendiente':  float(totales['recaudado_pendiente']),
            'total_depositado':     float(totales['depositado']),
            'pendiente':            float(totales['pendiente']),
            'sistema':              _sistema_json(sist),
            # Claves sueltas que ya usaba el front (se mantienen por compatibilidad).
            'sistema_boletas':      float(sist['boletas']),
            'sistema_adicionales':  float(sist['adicionales']),
            'sistema_total':        float(sist['total']),
            'sistema_cant':         sist['cant'],
        })


# ─────────────────────────────────────────────────────────────
# AJAX: eliminar recaudación (solo staff/superuser)
# ─────────────────────────────────────────────────────────────

class EliminarRecaudacionAjax(LoginRequiredMixin, View):
    def post(self, request):
        if not (request.user.is_staff or request.user.is_superuser):
            return JsonResponse(
                {'error': 'Solo administradores pueden eliminar recaudaciones.'},
                status=403
            )

        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        ids = data.get('ids', [])
        if not ids:
            return JsonResponse({'error': 'No se recibieron IDs.'}, status=400)
        try:
            ids = [int(i) for i in ids]
        except (ValueError, TypeError):
            return JsonResponse({'error': 'IDs inválidos.'}, status=400)

        cubiertas = list(
            RecaudacionDiaria.objects
            .filter(pk__in=ids, cubierta_por__isnull=False)
            .values_list('pk', flat=True)
        )
        if cubiertas:
            return JsonResponse({
                'error': f'La(s) recaudación(es) #{", #".join(map(str, cubiertas))} '
                         f'ya fueron cubiertas por un depósito, no se pueden eliminar.'
            }, status=400)

        with transaction.atomic():
            eliminados, _ = RecaudacionDiaria.objects.filter(pk__in=ids).delete()

        return JsonResponse({'success': True, 'eliminados': eliminados})


# ─────────────────────────────────────────────────────────────
# AJAX: estado de recaudación por entidad (para polling/refresh)
# ─────────────────────────────────────────────────────────────

class EstadoRecaudacionAjax(LoginRequiredMixin, View):
    """
    GET ?entidad=pagofacil|rapipago|western_union
    Devuelve el balance actualizado de esa entidad.
    """
    def get(self, request):
        entidad = request.GET.get('entidad', '').strip()
        if entidad not in ENTIDADES_VALIDAS:
            return JsonResponse({'error': 'Entidad inválida.'}, status=400)

        totales = _totales_por_entidad(entidad)

        # Últimas 5 recaudaciones PENDIENTES para refresh rápido de la tabla
        ultimas = [
            _recaudacion_as_dict(r)
            for r in RecaudacionDiaria.objects.filter(entidad=entidad, cubierta_por__isnull=True)
                                               .select_related('registrado_por')[:5]
        ]

        return JsonResponse({
            'entidad':             entidad,
            'total_recaudado':     float(totales['recaudado']),
            'recaudado_pendiente': float(totales['recaudado_pendiente']),
            'total_depositado':    float(totales['depositado']),
            'pendiente':           float(totales['pendiente']),
            'ultimas':             ultimas,
        })


class SistemaPorCanalAjax(LoginRequiredMixin, View):
    """
    GET ?entidad=pagofacil|rapipago|western_union&fecha=YYYY-MM-DD
    Devuelve lo que el sistema registró en cobros por ese canal ese día,
    para contrastarlo con la recaudación que se carga a mano.
    """
    def get(self, request):
        entidad = request.GET.get('entidad', '').strip()
        if entidad not in ENTIDADES_VALIDAS:
            return JsonResponse({'error': 'Entidad inválida.'}, status=400)

        fecha = parse_date(request.GET.get('fecha', '').strip())
        if fecha is None:
            return JsonResponse({'error': 'Fecha inválida.'}, status=400)

        s = _sistema_json(_sistema_por_canal(entidad, fecha))
        s.update({'entidad': entidad, 'fecha': str(fecha)})
        return JsonResponse(s)


# ─────────────────────────────────────────────────────────────
# BOLETAS DEL DÍA + CORRECCIÓN DE FACTURAS REDONDEADAS
# ─────────────────────────────────────────────────────────────


def _boletas_del_dia(entidad: str, fecha) -> list:
    """
    Cada boleta (ItemCobro) del canal de la entidad en esa fecha, con cómo
    se pagó su cobro y cuánto pesa en el número que se declara:
      factor 1   → se declara completa
      factor 0   → no se declara (PagoFácil: cobro pagado sin efectivo)
      factor 0-1 → cobro mixto en PagoFácil: parte proporcional al efectivo
    Mismo criterio que _sistema_por_canal(), para que la vista previa de
    "cómo queda con las correcciones" coincida con lo que se va a comparar.
    """
    canal = CANAL_POR_ENTIDAD.get(entidad)
    if canal is None or fecha is None:
        return []
    solo_efectivo = entidad in ENTIDADES_SOLO_EFECTIVO
    items = list(
        ItemCobro.objects
        .filter(cobro__estado=Cobro.ESTADO_CERRADO, canal=canal,
                cobro__fecha_cierre__date=fecha)
        .select_related('servicio', 'cobro')
        .order_by('cobro__fecha_cierre', 'cobro_id', 'orden', 'pk')
    )
    pagos = {}
    for p in (PagoCobro.objects.filter(cobro_id__in={i.cobro_id for i in items})
              .values('cobro_id', 'metodo').annotate(s=Sum('monto'))):
        pagos.setdefault(p['cobro_id'], {})
        pagos[p['cobro_id']][p['metodo']] = pagos[p['cobro_id']].get(p['metodo'], Decimal('0')) + p['s']
    nombres = dict(PagoCobro.METODOS)

    out = []
    for it in items:
        pg = {m: v for m, v in pagos.get(it.cobro_id, {}).items() if v > 0}
        tot = sum(pg.values(), Decimal('0'))
        efe = pg.get(PagoCobro.METODO_EFECTIVO, Decimal('0'))
        if efe <= 0 or tot <= 0:
            clase, factor = 'otros', (Decimal('0') if solo_efectivo else Decimal('1'))
        elif efe >= tot:
            clase, factor = 'efectivo', Decimal('1')
        else:
            clase, factor = 'mixto', (efe / tot if solo_efectivo else Decimal('1'))
        out.append({
            'id':          it.pk,
            'cobro_id':    it.cobro_id,
            'hora':        timezone.localtime(it.cobro.fecha_cierre).strftime('%H:%M'),
            'codigo':      it.servicio.codigo,
            'descripcion': it.servicio.descripcion,
            'cantidad':    it.cantidad or 1,
            'factura':     float(it.monto_servicio),
            'adicional':   float(it.monto_adicional - it.monto_redondeo),
            'redondeo':    float(it.monto_redondeo),
            'pago':        ' + '.join(nombres.get(m, m) for m in sorted(pg)) or 'Sin pago',
            'clase':       clase,
            'factor':      float(factor),
        })
    return out


class BoletasCanalAjax(LoginRequiredMixin, View):
    """
    GET  ?entidad=&fecha=  → las boletas del canal ese día (para revisarlas
         contra el listado de la plataforma).
    POST JSON { entidad, fecha, correcciones: [{item_id, factura_real}] }
         → corrige boletas que se cargaron con el redondeo ADENTRO de la
         factura (ej. boleta real $18.246,86 cargada como $18.300): la
         factura baja al importe real y la diferencia pasa a redondeo,
         que es parte del adicional (ganancia).

    Qué NO cambia: el total del cobro ni sus pagos → la caja, los cierres
    de turno y el efectivo esperado quedan igual. Qué SÍ cambia: baja lo
    que hay que declarar a la entidad y sube la ganancia en lo mismo. Si
    el turno ya tiene cierre diario, su total de adicionales/redondeos
    guardado sube en lo mismo (su total general no cambia).
    """
    def get(self, request):
        from .views_cobros import puede_editar_cobros
        entidad = request.GET.get('entidad', '').strip()
        if entidad not in ENTIDADES_VALIDAS:
            return JsonResponse({'error': 'Entidad inválida.'}, status=400)
        fecha = parse_date(request.GET.get('fecha', '').strip())
        if fecha is None:
            return JsonResponse({'error': 'Fecha inválida.'}, status=400)
        return JsonResponse({
            'boletas':        _boletas_del_dia(entidad, fecha),
            'puede_corregir': puede_editar_cobros(request.user),
        })

    def post(self, request):
        from .views_cobros import puede_editar_cobros
        if not puede_editar_cobros(request.user):
            return JsonResponse({'error': 'No tenés permiso para corregir cobros.'}, status=403)
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        entidad = (data.get('entidad') or '').strip()
        if entidad not in ENTIDADES_VALIDAS:
            return JsonResponse({'error': 'Entidad inválida.'}, status=400)
        fecha = parse_date((data.get('fecha') or '').strip())
        if fecha is None:
            return JsonResponse({'error': 'Fecha inválida.'}, status=400)

        pedidas = {}
        for c in data.get('correcciones') or []:
            try:
                item_id = int(c.get('item_id'))
                real = Decimal(str(c.get('factura_real'))).quantize(CENT)
            except (TypeError, ValueError, InvalidOperation, AttributeError):
                return JsonResponse({'error': 'Hay un importe inválido.'}, status=400)
            pedidas[item_id] = real
        if not pedidas:
            return JsonResponse({'error': 'No hay correcciones para guardar.'}, status=400)

        canal = CANAL_POR_ENTIDAD[entidad]
        autor = request.user.get_full_name() or request.user.username
        hoy = timezone.localtime().strftime('%d/%m/%Y')
        with transaction.atomic():
            items = {
                i.pk: i for i in
                ItemCobro.objects.select_for_update(of=('self',))
                .select_related('servicio', 'cobro')
                .filter(pk__in=pedidas.keys(), canal=canal,
                        cobro__estado=Cobro.ESTADO_CERRADO, cobro__fecha_cierre__date=fecha)
            }
            errores = []
            cambios = []
            for item_id, real in pedidas.items():
                it = items.get(item_id)
                if it is None:
                    errores.append(f'La boleta #{item_id} no es de este canal y fecha.')
                    continue
                cod = it.servicio.codigo
                if real <= 0:
                    errores.append(f'{cod}: el importe real tiene que ser mayor a cero.')
                    continue
                dif = it.monto_servicio - real
                if dif < 0:
                    errores.append(
                        f'{cod}: el importe real ({_pesos(real)}) es mayor que la factura cargada '
                        f'({_pesos(it.monto_servicio)}). Acá solo se saca el redondeo de la factura; '
                        f'para subirla, usá Editar en el historial de cobros.')
                    continue
                if dif > MAX_REDONDEO_FACTURA:
                    errores.append(
                        f'{cod}: la diferencia ({_pesos(dif)}) es demasiado grande para un redondeo '
                        f'(máximo {_pesos(MAX_REDONDEO_FACTURA)}). Revisá el número o corregilo desde '
                        f'el historial de cobros.')
                    continue
                if dif:
                    cambios.append((it, real, dif))
            if errores:
                return JsonResponse({'error': ' '.join(errores)}, status=400)

            total = Decimal('0')
            for it, real, dif in cambios:
                anterior = it.monto_servicio
                it.monto_servicio = real
                it.monto_adicional += dif
                it.monto_redondeo += dif
                it.save(update_fields=['monto_servicio', 'monto_adicional', 'monto_redondeo'])

                # Queda anotado en el cobro (se ve en el detalle del historial).
                cobro = Cobro.objects.select_for_update().get(pk=it.cobro_id)
                nota = (f'[{hoy} {autor}] Redondeo sacado de la factura {it.servicio.codigo}: '
                        f'{_pesos(anterior)} → {_pesos(real)} ({_pesos(dif)} pasan a redondeo).')
                cobro.observaciones = f'{cobro.observaciones}\n{nota}'.strip()
                cobro.save(update_fields=['observaciones'])

                cierre_id = (Cobro.objects.filter(pk=it.cobro_id)
                             .values_list('turno__cierre_diario_id', flat=True).first())
                if cierre_id:
                    cierre = CierreDiario.objects.select_for_update().get(pk=cierre_id)
                    cierre.total_adicionales += dif
                    cierre.total_redondeos += dif
                    cierre.save(update_fields=['total_adicionales', 'total_redondeos'])
                total += dif

        recalcular_redondeo_recaudaciones([fecha])
        s = _sistema_json(_sistema_por_canal(entidad, fecha))
        s.update({'entidad': entidad, 'fecha': str(fecha)})
        return JsonResponse({
            'success':        True,
            'corregidas':     len(cambios),
            'total_redondeo': float(total),
            'sistema':        s,
            'boletas':        _boletas_del_dia(entidad, fecha),
        })


class ComisionEntidadAjax(LoginRequiredMixin, View):
    """
    POST JSON { entidad, monto, vigente_desde (AAAA-MM-DD) } — solo staff.
    Registra un nuevo monto de comisión por boleta para la entidad. No pisa
    los anteriores: cada cambio es una fila nueva con su fecha de vigencia,
    así los días viejos se siguen calculando con el monto de ese momento.
    """
    def post(self, request):
        if not (request.user.is_staff or request.user.is_superuser):
            return JsonResponse({'error': 'Solo administradores pueden cambiar la comisión.'}, status=403)
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        entidad = (data.get('entidad') or '').strip()
        if entidad not in ENTIDADES_VALIDAS:
            return JsonResponse({'error': 'Entidad inválida.'}, status=400)
        try:
            monto = Decimal(str(data.get('monto', ''))).quantize(CENT)
            if monto < 0:
                raise ValueError
        except (InvalidOperation, ValueError):
            return JsonResponse({'error': 'El monto tiene que ser un número mayor o igual a 0.'}, status=400)
        desde = parse_date((data.get('vigente_desde') or '').strip())
        if desde is None:
            return JsonResponse({'error': 'Fecha "desde" inválida.'}, status=400)

        c = ComisionEntidad.objects.create(entidad=entidad, monto_por_boleta=monto,
                                           vigente_desde=desde, registrado_por=request.user)
        return JsonResponse({
            'success':       True,
            'id':            c.pk,
            'monto':         float(c.monto_por_boleta),
            'vigente_desde': str(c.vigente_desde),
        })


# ─────────────────────────────────────────────────────────────
# HISTORIAL COMPLETO (pendientes + cubiertas)
# ─────────────────────────────────────────────────────────────

class HistorialRecaudacionesView(LoginRequiredMixin, View):
    def get(self, request):
        desde   = request.GET.get('desde',   '').strip()
        hasta   = request.GET.get('hasta',   '').strip()
        entidad = request.GET.get('entidad', '').strip()
        estado  = request.GET.get('estado',  '').strip()  # '', 'pendiente', 'cubierta'

        qs = (
            RecaudacionDiaria.objects
            .select_related('registrado_por', 'cubierta_por')
            .all()
        )

        if desde:
            qs = qs.filter(fecha__gte=desde)
        if hasta:
            qs = qs.filter(fecha__lte=hasta)
        if entidad in ENTIDADES_VALIDAS:
            qs = qs.filter(entidad=entidad)
        if estado == 'pendiente':
            qs = qs.filter(cubierta_por__isnull=True)
        elif estado == 'cubierta':
            qs = qs.filter(cubierta_por__isnull=False)

        total_filtrado = qs.aggregate(t=Sum('monto'))['t'] or Decimal('0')

        def _total_ent(ent):
            return (qs.filter(entidad=ent).aggregate(t=Sum('monto'))['t']
                    or Decimal('0'))
        total_pf_filtrado = _total_ent(RecaudacionDiaria.ENTIDAD_PAGOFACIL)
        total_rp_filtrado = _total_ent(RecaudacionDiaria.ENTIDAD_RAPIPAGO)
        total_wu_filtrado = _total_ent(RecaudacionDiaria.ENTIDAD_WESTERN_UNION)

        return render(request, 'cobranzas/historial_recaudaciones.html', {
            'recaudaciones':      qs[:500],
            'desde':              desde,
            'hasta':              hasta,
            'entidad':            entidad,
            'estado':             estado,
            'total_filtrado':     total_filtrado,
            'total_pf_filtrado':  total_pf_filtrado,
            'total_rp_filtrado':  total_rp_filtrado,
            'total_wu_filtrado':  total_wu_filtrado,
            'ENTIDAD_PF':         RecaudacionDiaria.ENTIDAD_PAGOFACIL,
            'ENTIDAD_RP':         RecaudacionDiaria.ENTIDAD_RAPIPAGO,
            'ENTIDAD_WU':         RecaudacionDiaria.ENTIDAD_WESTERN_UNION,
        })