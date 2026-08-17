"""
views_ganancias.py
Ganancias por adicionales: total ganado (suma de ItemCobro.monto_adicional
de cobros cerrados), gastos/retiros registrados por persona, y saldo
disponible = ganado - gastado.
"""
import json
from decimal import Decimal, InvalidOperation

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Sum, Count
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views import View

from core.models import Usuario

from .models import Cobro, ItemCobro, GastoGanancia


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────

def _ganado_total() -> Decimal:
    """Suma de todos los adicionales de cobros cerrados (todo el historial)."""
    return (
        ItemCobro.objects
        .filter(cobro__estado=Cobro.ESTADO_CERRADO)
        .aggregate(t=Sum('monto_adicional'))['t'] or Decimal('0')
    )


def _gastado_total() -> Decimal:
    return GastoGanancia.objects.aggregate(t=Sum('monto'))['t'] or Decimal('0')


def _totales() -> dict:
    ganado  = _ganado_total()
    gastado = _gastado_total()
    saldo   = ganado - gastado
    return {
        'ganado':  ganado,
        'gastado': gastado,
        'saldo':   saldo,
    }


def _por_persona():
    return (
        GastoGanancia.objects
        .values('persona')
        .annotate(total=Sum('monto'), cantidad=Count('id'))
        .order_by('-total')
    )


def _gasto_as_dict(g: GastoGanancia) -> dict:
    return {
        'id':             g.pk,
        'fecha':          g.fecha.strftime('%d/%m/%Y'),
        'fecha_iso':      str(g.fecha),
        'persona':        g.persona,
        'motivo':         g.motivo,
        'monto':          float(g.monto),
        'observaciones':  g.observaciones or '',
        'registrado_por': (
            g.registrado_por.get_full_name() or g.registrado_por.username
            if g.registrado_por else '—'
        ),
    }


ORDENES = {
    'fecha_desc': ('-fecha', '-fecha_registro'),
    'fecha_asc':  ('fecha', 'fecha_registro'),
    'monto_desc': ('-monto',),
    'monto_asc':  ('monto',),
}


def _sugerencias_persona():
    """
    Nombres para el autocompletado del campo "persona" (que sigue siendo
    texto libre, no un FK): combina las personas ya usadas en gastos
    anteriores con los usuarios activos del sistema, por si la persona
    que retira plata también es alguien con cuenta en Kairos.
    """
    previas = set(
        GastoGanancia.objects.exclude(persona='').values_list('persona', flat=True)
    )
    usuarios = {
        u.get_full_name()
        for u in Usuario.objects.filter(is_active=True)
    }
    return sorted(previas | usuarios, key=str.lower)


def _gastos_filtrados(persona: str = '', desde=None, hasta=None, orden: str = 'fecha_desc'):
    qs = GastoGanancia.objects.select_related('registrado_por')
    if persona:
        qs = qs.filter(persona=persona)
    if desde:
        qs = qs.filter(fecha__gte=desde)
    if hasta:
        qs = qs.filter(fecha__lte=hasta)
    return qs.order_by(*ORDENES.get(orden, ORDENES['fecha_desc']))


# ─────────────────────────────────────────────────────────────
# VISTA PRINCIPAL
# ─────────────────────────────────────────────────────────────

class GananciasView(LoginRequiredMixin, View):
    def get(self, request):
        totales    = _totales()
        por_persona = list(_por_persona())
        gastos = _gastos_filtrados()[:30]
        personas_previas = _sugerencias_persona()

        totales_json = {k: float(v) for k, v in totales.items()}

        return render(request, 'cobranzas/ganancias.html', {
            'totales':          totales,
            'totales_json':     totales_json,
            'por_persona':      por_persona,
            'gastos':           gastos,
            'personas_previas': personas_previas,
            'hoy':              timezone.localdate(),
        })


# ─────────────────────────────────────────────────────────────
# AJAX: registrar gasto
# ─────────────────────────────────────────────────────────────

class RegistrarGastoAjax(LoginRequiredMixin, View):
    def post(self, request):
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        fecha_raw = data.get('fecha', '').strip()
        if not fecha_raw:
            return JsonResponse({'error': 'La fecha es obligatoria.'}, status=400)
        fecha = parse_date(fecha_raw)
        if fecha is None:
            return JsonResponse({'error': 'Fecha inválida. Usá el formato AAAA-MM-DD.'}, status=400)
        if fecha > timezone.localdate():
            return JsonResponse({'error': 'La fecha no puede ser futura.'}, status=400)

        persona = data.get('persona', '').strip()
        if not persona:
            return JsonResponse({'error': 'Indicá quién usó el dinero.'}, status=400)

        motivo = data.get('motivo', '').strip()
        if not motivo:
            return JsonResponse({'error': 'Indicá para qué se usó.'}, status=400)

        try:
            monto = Decimal(str(data.get('monto', 0)))
            if monto <= 0:
                raise ValueError
        except (ValueError, InvalidOperation):
            return JsonResponse({'error': 'El monto debe ser mayor a cero.'}, status=400)

        observaciones = data.get('observaciones', '').strip()

        with transaction.atomic():
            gasto = GastoGanancia.objects.create(
                fecha=fecha,
                persona=persona,
                motivo=motivo,
                monto=monto,
                observaciones=observaciones,
                registrado_por=request.user,
            )

        totales = _totales()

        return JsonResponse({
            'success':     True,
            'gasto':       _gasto_as_dict(gasto),
            'ganado':      float(totales['ganado']),
            'gastado':     float(totales['gastado']),
            'saldo':       float(totales['saldo']),
            'por_persona': list(_por_persona()),
        })


# ─────────────────────────────────────────────────────────────
# AJAX: listar gastos con filtro (persona, rango de fechas) y orden
# ─────────────────────────────────────────────────────────────

class ListarGastosAjax(LoginRequiredMixin, View):
    """
    GET ?persona=&desde=&hasta=&orden=fecha_desc|fecha_asc|monto_desc|monto_asc
    Devuelve los gastos que matchean, más la suma total del subconjunto
    filtrado (para mostrar "N gastos por $X" arriba de la tabla).
    """
    def get(self, request):
        persona = request.GET.get('persona', '').strip()
        orden   = request.GET.get('orden', 'fecha_desc').strip()
        if orden not in ORDENES:
            orden = 'fecha_desc'

        desde = parse_date(request.GET.get('desde', '').strip()) if request.GET.get('desde') else None
        hasta = parse_date(request.GET.get('hasta', '').strip()) if request.GET.get('hasta') else None

        qs = _gastos_filtrados(persona=persona, desde=desde, hasta=hasta, orden=orden)
        total_filtrado = qs.aggregate(t=Sum('monto'))['t'] or Decimal('0')

        return JsonResponse({
            'gastos':         [_gasto_as_dict(g) for g in qs[:200]],
            'cantidad':       qs.count(),
            'total_filtrado': float(total_filtrado),
        })


# ─────────────────────────────────────────────────────────────
# AJAX: eliminar gasto (solo staff/superuser)
# ─────────────────────────────────────────────────────────────

class EliminarGastoAjax(LoginRequiredMixin, View):
    def post(self, request):
        if not (request.user.is_staff or request.user.is_superuser):
            return JsonResponse(
                {'error': 'Solo administradores pueden eliminar gastos.'},
                status=403
            )

        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        gasto_id = data.get('id')
        if not gasto_id:
            return JsonResponse({'error': 'No se recibió el ID.'}, status=400)

        with transaction.atomic():
            eliminados, _ = GastoGanancia.objects.filter(pk=gasto_id).delete()

        if not eliminados:
            return JsonResponse({'error': 'No se encontró el gasto.'}, status=404)

        totales = _totales()
        return JsonResponse({
            'success':     True,
            'ganado':      float(totales['ganado']),
            'gastado':     float(totales['gastado']),
            'saldo':       float(totales['saldo']),
            'por_persona': list(_por_persona()),
        })
