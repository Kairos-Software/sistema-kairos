"""
views_caja.py
Vistas para la gestión de turnos, apertura/cierre de caja,
retiros y cierre diario.
"""
import json
from decimal import Decimal

from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View
from django.utils import timezone
from django.db import transaction
from django.db.models import Sum

from .models import Turno, RetiroCaja, Cobro, PagoCobro, CierreDiario


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
        'total_general':        float(turno.total_general()),
        'total_adicionales':    float(turno.total_adicionales()),
        'efectivo_esperado':    float(turno.efectivo_esperado()),
        'cant_cobros':          turno.cobros.filter(estado=Cobro.ESTADO_CERRADO).count(),
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
# AJAX: registrar retiro de caja
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
            motivo=motivo,
            monto=monto,
            registrado_por=request.user,
        )

        return JsonResponse({
            'success':           True,
            'retiro_id':         retiro.pk,
            'monto':             float(retiro.monto),
            'motivo':            retiro.motivo,
            'fecha':             retiro.fecha.strftime('%d/%m/%Y %H:%M'),
            'efectivo_esperado': float(turno.efectivo_esperado()),
            'total_retiros':     float(turno.total_retiros()),
        })

    def delete(self, request):
        """Anula un retiro por su ID."""
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
            from datetime import date
            desde = date.fromisoformat(desde_str)
            hasta = date.fromisoformat(hasta_str)
        except ValueError:
            return JsonResponse({'error': 'Formato de fecha inválido. Usá YYYY-MM-DD.'}, status=400)

        if desde > hasta:
            return JsonResponse({'error': 'La fecha "desde" no puede ser mayor que "hasta".'}, status=400)

        # No puede haber turno abierto
        if get_turno_abierto():
            return JsonResponse(
                {'error': 'Hay un turno abierto. Cerralo antes de hacer el cierre diario.'},
                status=400
            )

        # Turnos cerrados pendientes (sin cierre diario asignado) en el rango
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

        # Calcular totales sumando los cobros de esos turnos
        ids_turnos = list(turnos.values_list('pk', flat=True))

        pagos_qs = PagoCobro.objects.filter(
            cobro__turno_id__in=ids_turnos,
            cobro__estado=Cobro.ESTADO_CERRADO,
        )

        def _sum_metodo(metodo):
            return float(
                pagos_qs.filter(metodo=metodo).aggregate(t=Sum('monto'))['t'] or 0
            )

        from .models import ItemCobro
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
            RetiroCaja.objects.filter(turno_id__in=ids_turnos, activo=True)
            .aggregate(t=Sum('monto'))['t'] or 0
        )
        tot_general = tot_efe + tot_tra + tot_deb + tot_cre + tot_qr

        # Efectivo esperado en caja = monto_inicial(primer turno) + cobros efe - retiros
        # En cierre diario usamos el efectivo_esperado del ÚLTIMO turno del día,
        # ya que cada turno arranca con lo que dejó el anterior.
        monto_inicial_dia = float(turnos.first().monto_inicial)
        efectivo_esperado_dia = monto_inicial_dia + tot_efe - tot_ret

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
            from datetime import date
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

        from .models import ItemCobro
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
            RetiroCaja.objects.filter(turno_id__in=ids_turnos, activo=True)
            .aggregate(t=Sum('monto'))['t'] or 0
        )
        tot_general = tot_efe + tot_tra + tot_deb + tot_cre + tot_qr

        # Efectivo esperado en caja al cierre del día
        monto_inicial_dia = turnos.order_by('fecha_apertura').first().monto_inicial
        ef_esperado = monto_inicial_dia + tot_efe - tot_ret
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
                total_general       = tot_general,
                total_adicionales   = tot_adicionales,
                efectivo_fisico     = efectivo_fisico,
                diferencia_caja     = diferencia,
            )
            # Marcar los turnos como incluidos en este cierre
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
# HISTORIAL DE TURNOS
# ─────────────────────────────────────────────────────────────

class HistorialTurnosView(LoginRequiredMixin, View):
    def get(self, request):
        desde = request.GET.get('desde', '').strip()
        hasta = request.GET.get('hasta', '').strip()

        qs = Turno.objects.select_related('cajero', 'cierre_diario').all()

        if desde:
            qs = qs.filter(fecha_apertura__date__gte=desde)
        if hasta:
            qs = qs.filter(fecha_apertura__date__lte=hasta)

        return render(request, 'cobranzas/historial_turnos.html', {
            'turnos': qs[:200],
            'desde':  desde,
            'hasta':  hasta,
        })


# ─────────────────────────────────────────────────────────────
# HISTORIAL DE CIERRES DIARIOS
# ─────────────────────────────────────────────────────────────

class HistorialCierresDiariosView(LoginRequiredMixin, View):
    def get(self, request):
        desde = request.GET.get('desde', '').strip()
        hasta = request.GET.get('hasta', '').strip()

        qs = CierreDiario.objects.select_related('realizado_por').all()

        if desde:
            qs = qs.filter(fecha__date__gte=desde)
        if hasta:
            qs = qs.filter(fecha__date__lte=hasta)

        return render(request, 'cobranzas/historial_cierres.html', {
            'cierres': qs[:200],
            'desde':   desde,
            'hasta':   hasta,
        })
