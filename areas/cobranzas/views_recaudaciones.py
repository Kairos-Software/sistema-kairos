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

from .models import RecaudacionDiaria, DepositoBancario, AjusteSaldoFavor


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
    saldo_anterior = _ultima_diferencia(entidad) or Decimal('0')
    pendiente = _recaudado_pendiente(entidad) - saldo_anterior
    return {
        'recaudado':         recaudado,
        'depositado':        depositado,
        'pendiente':         pendiente,
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
        if entidad not in (RecaudacionDiaria.ENTIDAD_PAGOFACIL, RecaudacionDiaria.ENTIDAD_RAPIPAGO):
            entidad = RecaudacionDiaria.ENTIDAD_PAGOFACIL

        # Totales para los botones de entidad
        tot_pf = _totales_por_entidad(RecaudacionDiaria.ENTIDAD_PAGOFACIL)
        tot_rp = _totales_por_entidad(RecaudacionDiaria.ENTIDAD_RAPIPAGO)

        cant_pf = RecaudacionDiaria.objects.filter(entidad=RecaudacionDiaria.ENTIDAD_PAGOFACIL).count()
        cant_rp = RecaudacionDiaria.objects.filter(entidad=RecaudacionDiaria.ENTIDAD_RAPIPAGO).count()

        # Últimas recaudaciones de la entidad activa
        ultimas = (
            RecaudacionDiaria.objects
            .filter(entidad=entidad)
            .select_related('registrado_por')[:15]
        )

        # ¿Ya existe recaudación hoy para esta entidad? (para precargar el form)
        hoy = timezone.localdate()
        recaudacion_hoy = RecaudacionDiaria.objects.filter(entidad=entidad, fecha=hoy).first()

        tot_activo = tot_pf if entidad == RecaudacionDiaria.ENTIDAD_PAGOFACIL else tot_rp

        # CAMBIO: los totales se pasan como JSON (via json_script) en vez de
        # interpolar {{ valor|floatformat:2 }} directo en un <script>. Con
        # LANGUAGE_CODE=es-es, floatformat usa coma decimal ("50000,00"),
        # lo que generaba un literal numérico JS inválido y rompía TODO el
        # script de la página (incluido el botón "Registrar recaudación").
        totales_json = {
            'pagofacil': {k: float(v) for k, v in tot_pf.items()},
            'rapipago':  {k: float(v) for k, v in tot_rp.items()},
        }

        return render(request, 'cobranzas/recaudaciones.html', {
            'entidad':          entidad,
            'entidad_label':    'PagoFácil' if entidad == RecaudacionDiaria.ENTIDAD_PAGOFACIL else 'RapiPago',
            'ultimas':          ultimas,
            'tot_pf':           tot_pf,
            'tot_rp':           tot_rp,
            'tot_activo':       tot_activo,
            'totales_json':     totales_json,
            'cant_pf':          cant_pf,
            'cant_rp':          cant_rp,
            'recaudacion_hoy':  recaudacion_hoy,
            'ENTIDAD_PF':       RecaudacionDiaria.ENTIDAD_PAGOFACIL,
            'ENTIDAD_RP':       RecaudacionDiaria.ENTIDAD_RAPIPAGO,
            'hoy':              hoy,
        })


# ─────────────────────────────────────────────────────────────
# AJAX: registrar / modificar recaudación
# ─────────────────────────────────────────────────────────────

class RegistrarRecaudacionAjax(LoginRequiredMixin, View):
    """
    POST con JSON:
      { entidad, fecha, monto, observaciones }

    Comportamiento:
      - Si ya existe RecaudacionDiaria para (entidad, fecha) → actualiza el monto
        (se suma, no reemplaza — ver parámetro 'modo' abajo).
      - Si no existe → crea uno nuevo.

    Parámetro opcional 'modo':
      - 'reemplazar' (default): el monto enviado reemplaza al existente.
      - 'sumar': el monto se suma al existente.
    """
    def post(self, request):
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        entidad = data.get('entidad', '').strip()
        if entidad not in (RecaudacionDiaria.ENTIDAD_PAGOFACIL, RecaudacionDiaria.ENTIDAD_RAPIPAGO):
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
        modo          = data.get('modo', 'reemplazar')  # 'reemplazar' | 'sumar'

        with transaction.atomic():
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

        totales = _totales_por_entidad(entidad)

        return JsonResponse({
            'success':         True,
            'recaudacion':     _recaudacion_as_dict(rec),
            'es_nueva':        not bool(existente) if 'existente' in dir() else True,
            'total_recaudado': float(totales['recaudado']),
            'total_depositado':float(totales['depositado']),
            'pendiente':       float(totales['pendiente']),
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
    GET ?entidad=pagofacil|rapipago
    Devuelve el balance actualizado de esa entidad.
    """
    def get(self, request):
        entidad = request.GET.get('entidad', '').strip()
        if entidad not in (RecaudacionDiaria.ENTIDAD_PAGOFACIL, RecaudacionDiaria.ENTIDAD_RAPIPAGO):
            return JsonResponse({'error': 'Entidad inválida.'}, status=400)

        totales = _totales_por_entidad(entidad)

        # Últimas 5 recaudaciones para refresh rápido de la tabla
        ultimas = [
            _recaudacion_as_dict(r)
            for r in RecaudacionDiaria.objects.filter(entidad=entidad)
                                               .select_related('registrado_por')[:5]
        ]

        return JsonResponse({
            'entidad':          entidad,
            'total_recaudado':  float(totales['recaudado']),
            'total_depositado': float(totales['depositado']),
            'pendiente':        float(totales['pendiente']),
            'ultimas':          ultimas,
        })