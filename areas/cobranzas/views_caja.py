"""
views_caja.py
Vistas para la gestión de turnos, apertura/cierre de caja,
retiros y cierre diario.
"""
import json
import csv
from decimal import Decimal
from datetime import date

from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View
from django.utils import timezone
from django.db import transaction
from django.db.models import Sum, Q, Value, DecimalField, Subquery, OuterRef
from django.db.models.functions import Coalesce

from .models import Turno, RetiroCaja, Cobro, PagoCobro, CierreDiario, ItemCobro


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────

def get_turno_abierto():
    """Devuelve el turno abierto actual o None."""
    return Turno.objects.filter(estado=Turno.ESTADO_ABIERTO).first()


def _resumen_turno(turno):
    """Devuelve un dict con todos los totales del turno."""
    tot_efe   = float(turno.total_efectivo())
    tot_ret   = float(turno.total_retiros())
    tot_ing   = float(turno.total_ingresos())
    tot_ext   = float(turno.total_extracciones())
    retiros = [
        {
            'id':     r.pk,
            'tipo':   r.tipo,
            'motivo': r.motivo,
            'monto':  float(r.monto),
            'fecha':  r.fecha.strftime('%d/%m/%Y %H:%M'),
        }
        for r in turno.retiros.filter(activo=True).order_by('fecha')
    ]
    return {
        'id':                   turno.pk,
        'numero':               turno.numero,
        'estado':               turno.estado,
        'cajero':               str(turno.cajero),
        'fecha_apertura':       turno.fecha_apertura.strftime('%d/%m/%Y %H:%M'),
        'monto_inicial':        float(turno.monto_inicial),
        'total_efectivo':       tot_efe,
        'total_transferencia':  float(turno.total_transferencia()),
        'total_debito':         float(turno.total_debito()),
        'total_credito':        float(turno.total_credito()),
        'total_qr':             float(turno.total_qr()),
        'total_retiros':        tot_ret,
        'total_ingresos':       tot_ing,
        'total_extracciones':   tot_ext,
        'total_general':        float(turno.total_general()),
        'total_adicionales':    float(turno.total_adicionales()),
        'efectivo_esperado':    float(turno.efectivo_esperado()),
        'cant_cobros':          turno.cobros.filter(estado=Cobro.ESTADO_CERRADO).count(),
        'retiros':              retiros,
    }


# ─────────────────────────────────────────────────────────────
# VISTA PRINCIPAL: página de caja
# ─────────────────────────────────────────────────────────────

class CajaView(LoginRequiredMixin, View):
    def get(self, request):
        turno_abierto = get_turno_abierto()
        return render(request, 'cobranzas/caja.html', {
            'turno_abierto': turno_abierto,
        })


# ─────────────────────────────────────────────────────────────
# AJAX: estado actual de la caja
# ─────────────────────────────────────────────────────────────

class EstadoCajaAjax(LoginRequiredMixin, View):
    def get(self, request):
        turno = get_turno_abierto()
        if turno:
            return JsonResponse({'abierta': True, 'turno': _resumen_turno(turno)})
        return JsonResponse({'abierta': False, 'turno': None})


# ─────────────────────────────────────────────────────────────
# AJAX: abrir caja (crea un turno nuevo)
# ─────────────────────────────────────────────────────────────

class AbrirCajaAjax(LoginRequiredMixin, View):
    def post(self, request):
        if get_turno_abierto():
            return JsonResponse(
                {'error': 'Ya hay un turno abierto. Cerralo antes de abrir uno nuevo.'},
                status=400
            )

        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido'}, status=400)

        try:
            monto_inicial = Decimal(str(data.get('monto_inicial', 0)))
            if monto_inicial < 0:
                raise ValueError
        except (ValueError, Exception):
            return JsonResponse({'error': 'Monto inicial inválido.'}, status=400)

        with transaction.atomic():
            turno = Turno.objects.create(
                cajero=request.user,
                monto_inicial=monto_inicial,
                estado=Turno.ESTADO_ABIERTO,
            )

        return JsonResponse({'success': True, 'turno': _resumen_turno(turno)})


# ─────────────────────────────────────────────────────────────
# AJAX: cerrar turno
# ─────────────────────────────────────────────────────────────

class CerrarTurnoAjax(LoginRequiredMixin, View):
    def post(self, request):
        turno = get_turno_abierto()
        if not turno:
            return JsonResponse({'error': 'No hay turno abierto.'}, status=400)

        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido'}, status=400)

        try:
            efectivo_declarado = Decimal(str(data.get('efectivo_declarado', 0)))
            if efectivo_declarado < 0:
                raise ValueError
        except (ValueError, Exception):
            return JsonResponse({'error': 'Efectivo declarado inválido.'}, status=400)

        with transaction.atomic():
            tot_efe   = turno.total_efectivo()
            tot_ret   = turno.total_retiros()
            ef_esperado = turno.efectivo_esperado()
            diferencia  = efectivo_declarado - ef_esperado

            if diferencia > 0:
                tipo_dif = Turno.TIPO_DIF_SOBRANTE
            elif diferencia < 0:
                tipo_dif = Turno.TIPO_DIF_FALTANTE
            else:
                tipo_dif = Turno.TIPO_DIF_SIN_DIF

            turno.estado                  = Turno.ESTADO_CERRADO
            turno.fecha_cierre            = timezone.now()
            turno.efectivo_declarado      = efectivo_declarado
            turno.total_efectivo_sistema  = tot_efe
            turno.diferencia              = diferencia
            turno.tipo_diferencia         = tipo_dif
            turno.save()

        return JsonResponse({
            'success':             True,
            'numero':              turno.numero,
            'efectivo_esperado':   float(ef_esperado),
            'efectivo_declarado':  float(efectivo_declarado),
            'diferencia':          float(diferencia),
            'tipo_diferencia':     turno.get_tipo_diferencia_display(),
            'total_general':       float(turno.total_general()),
            'total_adicionales':   float(turno.total_adicionales()),
        })


# ─────────────────────────────────────────────────────────────
# AJAX: reabrir un turno cerrado
# ─────────────────────────────────────────────────────────────

class ReabrirTurnoAjax(LoginRequiredMixin, View):
    """
    Reabre un turno cerrado siempre que:
      - No tenga cierre diario asignado (ya consolidado = intocable).
      - No haya otro turno abierto en este momento.

    Al reabrir se limpian los campos de cierre (fecha_cierre,
    efectivo_declarado, total_efectivo_sistema, diferencia,
    tipo_diferencia) y el estado vuelve a ABIERTO.
    Los cobros y retiros del turno quedan intactos.
    """
    def post(self, request):
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido'}, status=400)

        turno_id = data.get('turno_id')
        if not turno_id:
            return JsonResponse({'error': 'turno_id requerido'}, status=400)

        turno = get_object_or_404(Turno, pk=turno_id)

        # Validaciones de negocio
        if turno.estado == Turno.ESTADO_ABIERTO:
            return JsonResponse({'error': 'El turno ya está abierto.'}, status=400)

        if turno.cierre_diario_id:
            return JsonResponse(
                {'error': (
                    f'El turno #{turno.numero} ya fue incluido en el Cierre #{turno.cierre_diario_id} '
                    f'y no puede reabrirse. El cierre diario consolida los datos de forma definitiva.'
                )},
                status=400
            )

        if get_turno_abierto():
            return JsonResponse(
                {'error': 'Ya hay un turno abierto. Cerralo antes de reabrir otro.'},
                status=400
            )

        with transaction.atomic():
            turno.estado                 = Turno.ESTADO_ABIERTO
            turno.fecha_cierre           = None
            turno.efectivo_declarado     = None
            turno.total_efectivo_sistema = None
            turno.diferencia             = None
            turno.tipo_diferencia        = None
            turno.save()

        return JsonResponse({
            'success': True,
            'turno_id': turno.pk,
            'numero': turno.numero,
        })


# ─────────────────────────────────────────────────────────────
# AJAX: registrar movimiento de caja (retiro o ingreso)
# ─────────────────────────────────────────────────────────────

class RetiroCajaAjax(LoginRequiredMixin, View):
    def post(self, request):
        turno = get_turno_abierto()
        if not turno:
            return JsonResponse({'error': 'No hay turno abierto.'}, status=400)

        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido'}, status=400)

        tipo = data.get('tipo', RetiroCaja.TIPO_RETIRO).strip()
        if tipo not in (RetiroCaja.TIPO_RETIRO, RetiroCaja.TIPO_INGRESO):
            return JsonResponse({'error': 'Tipo de movimiento inválido.'}, status=400)

        motivo = data.get('motivo', '').strip()
        if not motivo:
            return JsonResponse({'error': 'El motivo es obligatorio.'}, status=400)

        try:
            monto = Decimal(str(data.get('monto', 0)))
            if monto <= 0:
                raise ValueError
        except (ValueError, Exception):
            return JsonResponse({'error': 'El monto debe ser mayor a cero.'}, status=400)

        retiro = RetiroCaja.objects.create(
            turno=turno,
            tipo=tipo,
            motivo=motivo,
            monto=monto,
            registrado_por=request.user,
        )

        return JsonResponse({
            'success':           True,
            'retiro_id':         retiro.pk,
            'tipo':              retiro.tipo,
            'monto':             float(retiro.monto),
            'motivo':            retiro.motivo,
            'fecha':             retiro.fecha.strftime('%d/%m/%Y %H:%M'),
            'efectivo_esperado': float(turno.efectivo_esperado()),
            'total_retiros':     float(turno.total_retiros()),
            'total_ingresos':    float(turno.total_ingresos()),
        })

    def put(self, request):
        """Edita un movimiento (retiro o ingreso) ya registrado, por si el cajero se equivocó."""
        turno = get_turno_abierto()
        if not turno:
            return JsonResponse({'error': 'No hay turno abierto.'}, status=400)

        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido'}, status=400)

        tipo = data.get('tipo', RetiroCaja.TIPO_RETIRO).strip()
        if tipo not in (RetiroCaja.TIPO_RETIRO, RetiroCaja.TIPO_INGRESO):
            return JsonResponse({'error': 'Tipo de movimiento inválido.'}, status=400)

        motivo = data.get('motivo', '').strip()
        if not motivo:
            return JsonResponse({'error': 'El motivo es obligatorio.'}, status=400)

        try:
            monto = Decimal(str(data.get('monto', 0)))
            if monto <= 0:
                raise ValueError
        except (ValueError, Exception):
            return JsonResponse({'error': 'El monto debe ser mayor a cero.'}, status=400)

        retiro = get_object_or_404(RetiroCaja, pk=data.get('id'), turno=turno, activo=True)
        retiro.tipo   = tipo
        retiro.motivo = motivo
        retiro.monto  = monto
        retiro.save()

        return JsonResponse({
            'success':           True,
            'retiro_id':         retiro.pk,
            'tipo':              retiro.tipo,
            'monto':             float(retiro.monto),
            'motivo':            retiro.motivo,
            'fecha':             retiro.fecha.strftime('%d/%m/%Y %H:%M'),
            'efectivo_esperado': float(turno.efectivo_esperado()),
            'total_retiros':     float(turno.total_retiros()),
            'total_ingresos':    float(turno.total_ingresos()),
        })

    def delete(self, request):
        """Anula un movimiento (retiro o ingreso) por su ID."""
        turno = get_turno_abierto()
        if not turno:
            return JsonResponse({'error': 'No hay turno abierto.'}, status=400)

        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido'}, status=400)

        retiro = get_object_or_404(RetiroCaja, pk=data.get('id'), turno=turno)
        retiro.activo = False
        retiro.save()

        return JsonResponse({
            'success':           True,
            'efectivo_esperado': float(turno.efectivo_esperado()),
            'total_retiros':     float(turno.total_retiros()),
            'total_ingresos':    float(turno.total_ingresos()),
        })


# ─────────────────────────────────────────────────────────────
# AJAX: previsualizar cierre diario (sin guardar)
# ─────────────────────────────────────────────────────────────

class PrevisualizarCierreDiarioAjax(LoginRequiredMixin, View):
    def post(self, request):
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido'}, status=400)

        desde_str = (data.get('desde') or '').strip()
        hasta_str = (data.get('hasta') or '').strip()

        if not desde_str or not hasta_str:
            return JsonResponse({'error': 'Las fechas desde y hasta son obligatorias.'}, status=400)

        try:
            desde = date.fromisoformat(desde_str)
            hasta = date.fromisoformat(hasta_str)
        except ValueError:
            return JsonResponse({'error': 'Formato de fecha inválido. Usá YYYY-MM-DD.'}, status=400)

        if desde > hasta:
            return JsonResponse({'error': 'La fecha "desde" no puede ser mayor que "hasta".'}, status=400)

        if get_turno_abierto():
            return JsonResponse(
                {'error': 'Hay un turno abierto. Cerralo antes de hacer el cierre diario.'},
                status=400
            )

        turnos = Turno.objects.filter(
            estado=Turno.ESTADO_CERRADO,
            cierre_diario__isnull=True,
            fecha_apertura__date__gte=desde,
            fecha_apertura__date__lte=hasta,
        ).order_by('fecha_apertura')

        if not turnos.exists():
            return JsonResponse(
                {'error': 'No hay turnos cerrados pendientes en ese rango de fechas.'},
                status=400
            )

        ids_turnos = list(turnos.values_list('pk', flat=True))

        pagos_qs = PagoCobro.objects.filter(
            cobro__turno_id__in=ids_turnos,
            cobro__estado=Cobro.ESTADO_CERRADO,
        )

        def _sum_metodo(metodo):
            return float(
                pagos_qs.filter(metodo=metodo).aggregate(t=Sum('monto'))['t'] or 0
            )

        tot_adicionales = float(
            ItemCobro.objects.filter(
                cobro__turno_id__in=ids_turnos,
                cobro__estado=Cobro.ESTADO_CERRADO,
            ).aggregate(t=Sum('monto_adicional'))['t'] or 0
        )

        tot_efe   = _sum_metodo(PagoCobro.METODO_EFECTIVO)
        tot_tra   = _sum_metodo(PagoCobro.METODO_TRANSFERENCIA)
        tot_deb   = _sum_metodo(PagoCobro.METODO_DEBITO)
        tot_cre   = _sum_metodo(PagoCobro.METODO_CREDITO)
        tot_qr    = _sum_metodo(PagoCobro.METODO_QR)
        tot_ret   = float(
            RetiroCaja.objects.filter(turno_id__in=ids_turnos, activo=True, tipo=RetiroCaja.TIPO_RETIRO)
            .aggregate(t=Sum('monto'))['t'] or 0
        )
        tot_ing   = float(
            RetiroCaja.objects.filter(turno_id__in=ids_turnos, activo=True, tipo=RetiroCaja.TIPO_INGRESO)
            .aggregate(t=Sum('monto'))['t'] or 0
        )
        tot_ext   = float(
            ItemCobro.objects.filter(
                cobro__turno_id__in=ids_turnos, cobro__estado=Cobro.ESTADO_CERRADO,
                servicio__familia__iexact='EX',
            ).aggregate(t=Sum('monto_servicio'))['t'] or 0
        )
        tot_general = tot_efe + tot_tra + tot_deb + tot_cre + tot_qr

        monto_inicial_dia = float(turnos.first().monto_inicial)
        efectivo_esperado_dia = monto_inicial_dia + tot_efe + tot_ing - tot_ret - tot_ext

        resumen_turnos = []
        for t in turnos:
            resumen_turnos.append({
                'numero':    t.numero,
                'cajero':    str(t.cajero),
                'fecha':     t.fecha_apertura.strftime('%d/%m/%Y'),
                'tot_gral':  float(t.total_general()),
                'ef_decl':   float(t.efectivo_declarado or 0),
            })

        return JsonResponse({
            'success':            True,
            'cant_turnos':        turnos.count(),
            'total_efectivo':     tot_efe,
            'total_transferencia': tot_tra,
            'total_debito':       tot_deb,
            'total_credito':      tot_cre,
            'total_qr':           tot_qr,
            'total_retiros':      tot_ret,
            'total_ingresos':     tot_ing,
            'total_extracciones': tot_ext,
            'total_general':      tot_general,
            'total_adicionales':  tot_adicionales,
            'efectivo_esperado':  efectivo_esperado_dia,
            'turnos':             resumen_turnos,
        })


# ─────────────────────────────────────────────────────────────
# AJAX: ejecutar cierre diario
# ─────────────────────────────────────────────────────────────

class EjecutarCierreDiarioAjax(LoginRequiredMixin, View):
    def post(self, request):
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido'}, status=400)

        desde_str = (data.get('desde') or '').strip()
        hasta_str = (data.get('hasta') or '').strip()

        try:
            desde = date.fromisoformat(desde_str)
            hasta = date.fromisoformat(hasta_str)
        except ValueError:
            return JsonResponse({'error': 'Fechas inválidas.'}, status=400)

        try:
            efectivo_fisico = Decimal(str(data.get('efectivo_fisico', 0)))
            if efectivo_fisico < 0:
                raise ValueError
        except (ValueError, Exception):
            return JsonResponse({'error': 'Efectivo físico inválido.'}, status=400)

        if get_turno_abierto():
            return JsonResponse(
                {'error': 'Hay un turno abierto. Cerralo primero.'},
                status=400
            )

        turnos = Turno.objects.filter(
            estado=Turno.ESTADO_CERRADO,
            cierre_diario__isnull=True,
            fecha_apertura__date__gte=desde,
            fecha_apertura__date__lte=hasta,
        )

        if not turnos.exists():
            return JsonResponse({'error': 'No hay turnos pendientes en ese rango.'}, status=400)

        ids_turnos = list(turnos.values_list('pk', flat=True))

        pagos_qs = PagoCobro.objects.filter(
            cobro__turno_id__in=ids_turnos,
            cobro__estado=Cobro.ESTADO_CERRADO,
        )

        def _sum_metodo(metodo):
            return Decimal(
                pagos_qs.filter(metodo=metodo).aggregate(t=Sum('monto'))['t'] or 0
            )

        tot_adicionales = Decimal(
            ItemCobro.objects.filter(
                cobro__turno_id__in=ids_turnos,
                cobro__estado=Cobro.ESTADO_CERRADO,
            ).aggregate(t=Sum('monto_adicional'))['t'] or 0
        )

        tot_efe  = _sum_metodo(PagoCobro.METODO_EFECTIVO)
        tot_tra  = _sum_metodo(PagoCobro.METODO_TRANSFERENCIA)
        tot_deb  = _sum_metodo(PagoCobro.METODO_DEBITO)
        tot_cre  = _sum_metodo(PagoCobro.METODO_CREDITO)
        tot_qr   = _sum_metodo(PagoCobro.METODO_QR)
        tot_ret  = Decimal(
            RetiroCaja.objects.filter(turno_id__in=ids_turnos, activo=True, tipo=RetiroCaja.TIPO_RETIRO)
            .aggregate(t=Sum('monto'))['t'] or 0
        )
        tot_ing  = Decimal(
            RetiroCaja.objects.filter(turno_id__in=ids_turnos, activo=True, tipo=RetiroCaja.TIPO_INGRESO)
            .aggregate(t=Sum('monto'))['t'] or 0
        )
        tot_ext  = Decimal(
            ItemCobro.objects.filter(
                cobro__turno_id__in=ids_turnos, cobro__estado=Cobro.ESTADO_CERRADO,
                servicio__familia__iexact='EX',
            ).aggregate(t=Sum('monto_servicio'))['t'] or 0
        )
        tot_general = tot_efe + tot_tra + tot_deb + tot_cre + tot_qr

        monto_inicial_dia = turnos.order_by('fecha_apertura').first().monto_inicial
        ef_esperado = monto_inicial_dia + tot_efe + tot_ing - tot_ret - tot_ext
        diferencia  = efectivo_fisico - ef_esperado

        with transaction.atomic():
            cierre = CierreDiario.objects.create(
                fecha_desde         = desde,
                fecha_hasta         = hasta,
                realizado_por       = request.user,
                cant_turnos         = turnos.count(),
                total_efectivo      = tot_efe,
                total_transferencia = tot_tra,
                total_debito        = tot_deb,
                total_credito       = tot_cre,
                total_qr            = tot_qr,
                total_retiros       = tot_ret,
                total_ingresos      = tot_ing,
                total_extracciones  = tot_ext,
                total_general       = tot_general,
                total_adicionales   = tot_adicionales,
                efectivo_fisico     = efectivo_fisico,
                diferencia_caja     = diferencia,
            )
            turnos.update(cierre_diario=cierre)

        return JsonResponse({
            'success':           True,
            'cierre_id':         cierre.pk,
            'cant_turnos':       cierre.cant_turnos,
            'total_general':     float(cierre.total_general),
            'total_adicionales': float(cierre.total_adicionales),
            'efectivo_fisico':   float(cierre.efectivo_fisico),
            'diferencia_caja':   float(cierre.diferencia_caja),
            'fecha':             cierre.fecha.strftime('%d/%m/%Y %H:%M'),
        })


# ─────────────────────────────────────────────────────────────
# HISTORIAL DE TURNOS (con filtros avanzados)
# ─────────────────────────────────────────────────────────────

class HistorialTurnosView(LoginRequiredMixin, View):
    def get(self, request):
        # Obtener parámetros de filtro
        desde = request.GET.get('desde', '').strip()
        hasta = request.GET.get('hasta', '').strip()
        estado = request.GET.get('estado', '')
        metodos_raw = request.GET.getlist('metodos') or request.GET.get('metodos', '').split(',')
        metodos = [m for m in metodos_raw if m]  # limpiar vacíos
        canales_raw = request.GET.getlist('canales') or request.GET.get('canales', '').split(',')
        canales = [c for c in canales_raw if c]
        diferencia = request.GET.get('diferencia', '')
        tiene_cierre = request.GET.get('tiene_cierre', '')
        order_by = request.GET.get('order_by', '-fecha_apertura')

        # Base queryset con relaciones necesarias
        qs = Turno.objects.select_related('cajero', 'cierre_diario')

        # Filtros de fecha
        if desde:
            qs = qs.filter(fecha_apertura__date__gte=desde)
        if hasta:
            qs = qs.filter(fecha_apertura__date__lte=hasta)

        # Filtro por estado
        if estado:
            qs = qs.filter(estado=estado)

        # Filtro por si tiene cierre diario asignado
        if tiene_cierre == 'si':
            qs = qs.filter(cierre_diario__isnull=False)
        elif tiene_cierre == 'no':
            qs = qs.filter(cierre_diario__isnull=True)

        # Filtro por tipo de diferencia (solo para turnos cerrados)
        if diferencia:
            qs = qs.filter(tipo_diferencia=diferencia)

        # Subconsultas para totales por método y canal
        subq_efe = Subquery(
            PagoCobro.objects.filter(
                cobro__turno=OuterRef('pk'),
                cobro__estado=Cobro.ESTADO_CERRADO,
                metodo=PagoCobro.METODO_EFECTIVO
            ).values('cobro__turno').annotate(s=Sum('monto')).values('s')[:1]
        )
        subq_tra = Subquery(
            PagoCobro.objects.filter(
                cobro__turno=OuterRef('pk'),
                cobro__estado=Cobro.ESTADO_CERRADO,
                metodo=PagoCobro.METODO_TRANSFERENCIA
            ).values('cobro__turno').annotate(s=Sum('monto')).values('s')[:1]
        )
        subq_deb = Subquery(
            PagoCobro.objects.filter(
                cobro__turno=OuterRef('pk'),
                cobro__estado=Cobro.ESTADO_CERRADO,
                metodo=PagoCobro.METODO_DEBITO
            ).values('cobro__turno').annotate(s=Sum('monto')).values('s')[:1]
        )
        subq_cre = Subquery(
            PagoCobro.objects.filter(
                cobro__turno=OuterRef('pk'),
                cobro__estado=Cobro.ESTADO_CERRADO,
                metodo=PagoCobro.METODO_CREDITO
            ).values('cobro__turno').annotate(s=Sum('monto')).values('s')[:1]
        )
        subq_qr = Subquery(
            PagoCobro.objects.filter(
                cobro__turno=OuterRef('pk'),
                cobro__estado=Cobro.ESTADO_CERRADO,
                metodo=PagoCobro.METODO_QR
            ).values('cobro__turno').annotate(s=Sum('monto')).values('s')[:1]
        )

        subq_pf = Subquery(
            ItemCobro.objects.filter(
                cobro__turno=OuterRef('pk'),
                cobro__estado=Cobro.ESTADO_CERRADO,
                canal=ItemCobro.CANAL_PAGOFACIL
            ).values('cobro__turno').annotate(s=Sum('monto_servicio')).values('s')[:1]
        )
        subq_rp = Subquery(
            ItemCobro.objects.filter(
                cobro__turno=OuterRef('pk'),
                cobro__estado=Cobro.ESTADO_CERRADO,
                canal=ItemCobro.CANAL_RAPIPAGO
            ).values('cobro__turno').annotate(s=Sum('monto_servicio')).values('s')[:1]
        )
        subq_otro = Subquery(
            ItemCobro.objects.filter(
                cobro__turno=OuterRef('pk'),
                cobro__estado=Cobro.ESTADO_CERRADO,
                canal=ItemCobro.CANAL_OTRO
            ).values('cobro__turno').annotate(s=Sum('monto_servicio')).values('s')[:1]
        )

        qs = qs.annotate(
            total_efe=Coalesce(subq_efe, Value(0, output_field=DecimalField())),
            total_tra=Coalesce(subq_tra, Value(0, output_field=DecimalField())),
            total_deb=Coalesce(subq_deb, Value(0, output_field=DecimalField())),
            total_cre=Coalesce(subq_cre, Value(0, output_field=DecimalField())),
            total_qr=Coalesce(subq_qr, Value(0, output_field=DecimalField())),
            total_pf=Coalesce(subq_pf, Value(0, output_field=DecimalField())),
            total_rp=Coalesce(subq_rp, Value(0, output_field=DecimalField())),
            total_otro=Coalesce(subq_otro, Value(0, output_field=DecimalField())),
        )

        # Filtrar por métodos: si se seleccionaron, el turno debe tener algún monto > 0 en esos métodos
        if metodos:
            q_metodos = Q()
            for met in metodos:
                if met == PagoCobro.METODO_EFECTIVO:
                    q_metodos |= Q(total_efe__gt=0)
                elif met == PagoCobro.METODO_TRANSFERENCIA:
                    q_metodos |= Q(total_tra__gt=0)
                elif met == PagoCobro.METODO_DEBITO:
                    q_metodos |= Q(total_deb__gt=0)
                elif met == PagoCobro.METODO_CREDITO:
                    q_metodos |= Q(total_cre__gt=0)
                elif met == PagoCobro.METODO_QR:
                    q_metodos |= Q(total_qr__gt=0)
            qs = qs.filter(q_metodos)

        # Filtrar por canales
        if canales:
            q_canales = Q()
            for can in canales:
                if can == ItemCobro.CANAL_PAGOFACIL:
                    q_canales |= Q(total_pf__gt=0)
                elif can == ItemCobro.CANAL_RAPIPAGO:
                    q_canales |= Q(total_rp__gt=0)
                elif can == ItemCobro.CANAL_OTRO:
                    q_canales |= Q(total_otro__gt=0)
            qs = qs.filter(q_canales)

        # Ordenamiento
        if order_by in ('numero', 'fecha_apertura', 'fecha_cierre', 'estado', 'monto_inicial', 'total_general'):
            qs = qs.order_by(order_by)
        else:
            qs = qs.order_by('-fecha_apertura')

        # Limitar a últimos 500 para performance
        turnos = qs[:500]

        return render(request, 'cobranzas/historial_turnos.html', {
            'turnos': turnos,
            'desde':  desde,
            'hasta':  hasta,
            'estado': estado,
            'metodos_seleccionados': metodos,
            'canales_seleccionados': canales,
            'diferencia': diferencia,
            'tiene_cierre': tiene_cierre,
            'order_by': order_by,
        })


# ─────────────────────────────────────────────────────────────
# EXPORTAR TURNOS A CSV
# ─────────────────────────────────────────────────────────────

def export_turnos_csv(request):
    """Exportar los turnos filtrados a CSV (mismos filtros que HistorialTurnosView)"""
    if not request.user.is_authenticated:
        return HttpResponse("No autorizado", status=401)

    desde = request.GET.get('desde', '').strip()
    hasta = request.GET.get('hasta', '').strip()
    estado = request.GET.get('estado', '')
    metodos_raw = request.GET.getlist('metodos') or request.GET.get('metodos', '').split(',')
    metodos = [m for m in metodos_raw if m]
    canales_raw = request.GET.getlist('canales') or request.GET.get('canales', '').split(',')
    canales = [c for c in canales_raw if c]
    diferencia = request.GET.get('diferencia', '')
    tiene_cierre = request.GET.get('tiene_cierre', '')

    qs = Turno.objects.select_related('cajero', 'cierre_diario')

    if desde:
        qs = qs.filter(fecha_apertura__date__gte=desde)
    if hasta:
        qs = qs.filter(fecha_apertura__date__lte=hasta)
    if estado:
        qs = qs.filter(estado=estado)
    if tiene_cierre == 'si':
        qs = qs.filter(cierre_diario__isnull=False)
    elif tiene_cierre == 'no':
        qs = qs.filter(cierre_diario__isnull=True)
    if diferencia:
        qs = qs.filter(tipo_diferencia=diferencia)

    # Subconsultas
    subq_efe = Subquery(
        PagoCobro.objects.filter(cobro__turno=OuterRef('pk'), cobro__estado=Cobro.ESTADO_CERRADO, metodo=PagoCobro.METODO_EFECTIVO)
        .values('cobro__turno').annotate(s=Sum('monto')).values('s')[:1]
    )
    subq_tra = Subquery(
        PagoCobro.objects.filter(cobro__turno=OuterRef('pk'), cobro__estado=Cobro.ESTADO_CERRADO, metodo=PagoCobro.METODO_TRANSFERENCIA)
        .values('cobro__turno').annotate(s=Sum('monto')).values('s')[:1]
    )
    subq_deb = Subquery(
        PagoCobro.objects.filter(cobro__turno=OuterRef('pk'), cobro__estado=Cobro.ESTADO_CERRADO, metodo=PagoCobro.METODO_DEBITO)
        .values('cobro__turno').annotate(s=Sum('monto')).values('s')[:1]
    )
    subq_cre = Subquery(
        PagoCobro.objects.filter(cobro__turno=OuterRef('pk'), cobro__estado=Cobro.ESTADO_CERRADO, metodo=PagoCobro.METODO_CREDITO)
        .values('cobro__turno').annotate(s=Sum('monto')).values('s')[:1]
    )
    subq_qr = Subquery(
        PagoCobro.objects.filter(cobro__turno=OuterRef('pk'), cobro__estado=Cobro.ESTADO_CERRADO, metodo=PagoCobro.METODO_QR)
        .values('cobro__turno').annotate(s=Sum('monto')).values('s')[:1]
    )
    subq_pf = Subquery(
        ItemCobro.objects.filter(cobro__turno=OuterRef('pk'), cobro__estado=Cobro.ESTADO_CERRADO, canal=ItemCobro.CANAL_PAGOFACIL)
        .values('cobro__turno').annotate(s=Sum('monto_servicio')).values('s')[:1]
    )
    subq_rp = Subquery(
        ItemCobro.objects.filter(cobro__turno=OuterRef('pk'), cobro__estado=Cobro.ESTADO_CERRADO, canal=ItemCobro.CANAL_RAPIPAGO)
        .values('cobro__turno').annotate(s=Sum('monto_servicio')).values('s')[:1]
    )
    subq_otro = Subquery(
        ItemCobro.objects.filter(cobro__turno=OuterRef('pk'), cobro__estado=Cobro.ESTADO_CERRADO, canal=ItemCobro.CANAL_OTRO)
        .values('cobro__turno').annotate(s=Sum('monto_servicio')).values('s')[:1]
    )

    qs = qs.annotate(
        total_efe=Coalesce(subq_efe, Value(0, output_field=DecimalField())),
        total_tra=Coalesce(subq_tra, Value(0, output_field=DecimalField())),
        total_deb=Coalesce(subq_deb, Value(0, output_field=DecimalField())),
        total_cre=Coalesce(subq_cre, Value(0, output_field=DecimalField())),
        total_qr=Coalesce(subq_qr, Value(0, output_field=DecimalField())),
        total_pf=Coalesce(subq_pf, Value(0, output_field=DecimalField())),
        total_rp=Coalesce(subq_rp, Value(0, output_field=DecimalField())),
        total_otro=Coalesce(subq_otro, Value(0, output_field=DecimalField())),
    )

    if metodos:
        q_metodos = Q()
        for met in metodos:
            if met == PagoCobro.METODO_EFECTIVO:
                q_metodos |= Q(total_efe__gt=0)
            elif met == PagoCobro.METODO_TRANSFERENCIA:
                q_metodos |= Q(total_tra__gt=0)
            elif met == PagoCobro.METODO_DEBITO:
                q_metodos |= Q(total_deb__gt=0)
            elif met == PagoCobro.METODO_CREDITO:
                q_metodos |= Q(total_cre__gt=0)
            elif met == PagoCobro.METODO_QR:
                q_metodos |= Q(total_qr__gt=0)
        qs = qs.filter(q_metodos)

    if canales:
        q_canales = Q()
        for can in canales:
            if can == ItemCobro.CANAL_PAGOFACIL:
                q_canales |= Q(total_pf__gt=0)
            elif can == ItemCobro.CANAL_RAPIPAGO:
                q_canales |= Q(total_rp__gt=0)
            elif can == ItemCobro.CANAL_OTRO:
                q_canales |= Q(total_otro__gt=0)
        qs = qs.filter(q_canales)

    qs = qs.order_by('fecha_apertura')

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="turnos_export.csv"'
    writer = csv.writer(response, delimiter=';')
    writer.writerow([
        'Número', 'Cajero', 'Fecha apertura', 'Fecha cierre', 'Estado',
        'Fondo inicial', 'Total efectivo', 'Total transferencia', 'Total débito',
        'Total crédito', 'Total QR', 'Total retiros', 'Total ingresos', 'Total extracciones',
        'Total general', 'Total PagoFácil', 'Total Rapipago', 'Total Otro canal',
        'Efectivo declarado', 'Diferencia', 'Cierre diario ID'
    ])

    for t in qs:
        writer.writerow([
            t.numero,
            str(t.cajero),
            t.fecha_apertura.strftime('%Y-%m-%d %H:%M:%S'),
            t.fecha_cierre.strftime('%Y-%m-%d %H:%M:%S') if t.fecha_cierre else '',
            t.get_estado_display(),
            float(t.monto_inicial),
            float(getattr(t, 'total_efe', 0)),
            float(getattr(t, 'total_tra', 0)),
            float(getattr(t, 'total_deb', 0)),
            float(getattr(t, 'total_cre', 0)),
            float(getattr(t, 'total_qr', 0)),
            float(t.total_retiros()),
            float(t.total_ingresos()),
            float(t.total_extracciones()),
            float(t.total_general()),
            float(getattr(t, 'total_pf', 0)),
            float(getattr(t, 'total_rp', 0)),
            float(getattr(t, 'total_otro', 0)),
            float(t.efectivo_declarado or 0),
            float(t.diferencia or 0),
            t.cierre_diario_id or '',
        ])

    return response


# ─────────────────────────────────────────────────────────────
# AJAX: turnos pendientes de cierre diario
# ─────────────────────────────────────────────────────────────

class TurnosPendientesAjax(LoginRequiredMixin, View):
    def get(self, request):
        from django.db.models import Min, Max
        pendientes = Turno.objects.filter(
            estado=Turno.ESTADO_CERRADO,
            cierre_diario__isnull=True,
        )
        count = pendientes.count()
        if count == 0:
            return JsonResponse({'count': 0, 'desde': None, 'hasta': None})
        agg = pendientes.aggregate(
            desde=Min('fecha_apertura'),
            hasta=Max('fecha_apertura'),
        )
        desde_str = agg['desde'].date().isoformat() if agg['desde'] else None
        hasta_str  = agg['hasta'].date().isoformat()  if agg['hasta']  else None
        return JsonResponse({'count': count, 'desde': desde_str, 'hasta': hasta_str})


# ─────────────────────────────────────────────────────────────
# HISTORIAL DE CIERRES DIARIOS
# ─────────────────────────────────────────────────────────────

class HistorialCierresDiariosView(LoginRequiredMixin, View):
    def get(self, request):
        desde = request.GET.get('desde', '').strip()
        hasta = request.GET.get('hasta', '').strip()
        diferencia = request.GET.get('diferencia', '')
        metodos_raw = request.GET.getlist('metodos') or request.GET.get('metodos', '').split(',')
        metodos = [m for m in metodos_raw if m]

        qs = CierreDiario.objects.select_related('realizado_por').all()

        if desde:
            qs = qs.filter(fecha__date__gte=desde)
        if hasta:
            qs = qs.filter(fecha__date__lte=hasta)

        # Filtro por diferencia
        if diferencia == 'sobrante':
            qs = qs.filter(diferencia_caja__gt=0)
        elif diferencia == 'faltante':
            qs = qs.filter(diferencia_caja__lt=0)
        elif diferencia == 'sin_diferencia':
            qs = qs.filter(diferencia_caja=0)

        # Filtro por métodos de pago: mostrar cierres que tengan al menos un monto >0 en los métodos seleccionados
        if metodos:
            q_metodos = Q()
            for met in metodos:
                if met == PagoCobro.METODO_EFECTIVO:
                    q_metodos |= Q(total_efectivo__gt=0)
                elif met == PagoCobro.METODO_TRANSFERENCIA:
                    q_metodos |= Q(total_transferencia__gt=0)
                elif met == PagoCobro.METODO_DEBITO:
                    q_metodos |= Q(total_debito__gt=0)
                elif met == PagoCobro.METODO_CREDITO:
                    q_metodos |= Q(total_credito__gt=0)
                elif met == PagoCobro.METODO_QR:
                    q_metodos |= Q(total_qr__gt=0)
            qs = qs.filter(q_metodos)

        qs = qs.order_by('-fecha')

        return render(request, 'cobranzas/historial_cierres.html', {
            'cierres': qs[:200],
            'desde': desde,
            'hasta': hasta,
            'diferencia': diferencia,
            'metodos_seleccionados': metodos,
        })


# ─────────────────────────────────────────────────────────────
# AJAX: eliminar turnos (solo staff/superuser)
# ─────────────────────────────────────────────────────────────

class EliminarTurnosAjax(LoginRequiredMixin, View):
    def post(self, request):
        if not (request.user.is_staff or request.user.is_superuser):
            return JsonResponse({'error': 'Solo administradores pueden eliminar turnos.'}, status=403)
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido'}, status=400)

        ids = data.get('ids', [])
        if not ids:
            return JsonResponse({'error': 'No se recibieron IDs.'}, status=400)
        try:
            ids = [int(i) for i in ids]
        except (ValueError, TypeError):
            return JsonResponse({'error': 'IDs inválidos.'}, status=400)

        with transaction.atomic():
            Cobro.objects.filter(turno_id__in=ids).delete()
            eliminados, _ = Turno.objects.filter(pk__in=ids).delete()

        return JsonResponse({'success': True, 'eliminados': eliminados})


class EliminarCierresAjax(LoginRequiredMixin, View):
    def post(self, request):
        if not (request.user.is_staff or request.user.is_superuser):
            return JsonResponse({'error': 'Solo administradores pueden eliminar cierres.'}, status=403)
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido'}, status=400)

        ids = data.get('ids', [])
        if not ids:
            return JsonResponse({'error': 'No se recibieron IDs.'}, status=400)
        try:
            ids = [int(i) for i in ids]
        except (ValueError, TypeError):
            return JsonResponse({'error': 'IDs inválidos.'}, status=400)

        with transaction.atomic():
            Turno.objects.filter(cierre_diario_id__in=ids).update(cierre_diario=None)
            eliminados, _ = CierreDiario.objects.filter(pk__in=ids).delete()

        return JsonResponse({'success': True, 'eliminados': eliminados})