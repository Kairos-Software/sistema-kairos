"""
views_caja_grande.py
Vistas para la Caja Grande (acumulado global de todos los cierres).
Los depósitos bancarios se gestionan desde views_depositos.py.

Caja Grande = SUM(CierreDiario.total_general)
              (histórico total recaudado, sin relación directa con depósitos)
"""
from decimal import Decimal

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Sum
from django.http import JsonResponse
from django.shortcuts import render
from django.views import View

from .models import CierreDiario, DepositoBancario, ItemCobro, Cobro, ExtraccionCajaGrande


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────

def get_total_caja_grande() -> Decimal:
    """Suma de total_general de todos los CierreDiario."""
    return (
        CierreDiario.objects
        .aggregate(t=Sum('total_general'))['t'] or Decimal('0')
    )


def get_total_depositado() -> Decimal:
    """Suma de todos los depósitos bancarios registrados."""
    return (
        DepositoBancario.objects
        .aggregate(t=Sum('monto'))['t'] or Decimal('0')
    )


def get_total_extracciones() -> Decimal:
    """
    Efectivo entregado, en toda la historia, por servicios de familia EX
    (extracciones). Ese efectivo sale de lo recaudado antes de llegar
    a depositarse, así que se descuenta de "pendiente de depositar".
    """
    return (
        ItemCobro.objects
        .filter(cobro__estado=Cobro.ESTADO_CERRADO, servicio__familia__iexact='EX')
        .aggregate(t=Sum('monto_servicio'))['t'] or Decimal('0')
    )


def get_pendiente_caja_grande() -> Decimal:
    """
    Efectivo realmente disponible para depositar: lo recaudado, menos lo
    ya depositado, menos lo entregado por extracciones (que nunca llega a
    depositarse porque se le dio en mano al cliente).
    """
    return get_total_caja_grande() - get_total_depositado() - get_total_extracciones()


# ─────────────────────────────────────────────────────────────
# VISTA: Caja Grande
# ─────────────────────────────────────────────────────────────

class CajaGrandeView(LoginRequiredMixin, View):
    def get(self, request):
        total_recaudado    = get_total_caja_grande()
        total_depositado   = get_total_depositado()
        total_extracciones = get_total_extracciones()
        pendiente           = total_recaudado - total_depositado - total_extracciones

        cant_cierres   = CierreDiario.objects.count()
        cant_depositos = DepositoBancario.objects.count()

        def _dep_ent(ent):
            return (DepositoBancario.objects.filter(entidad=ent)
                    .aggregate(t=Sum('monto'))['t'] or Decimal('0'))
        depositos_pf = _dep_ent(DepositoBancario.ENTIDAD_PAGOFACIL)
        depositos_rp = _dep_ent(DepositoBancario.ENTIDAD_RAPIPAGO)
        depositos_wu = _dep_ent(DepositoBancario.ENTIDAD_WESTERN_UNION)

        ultimos_cierres = (
            CierreDiario.objects
            .select_related('realizado_por')[:8]
        )

        extracciones_caja_grande = (
            ExtraccionCajaGrande.objects
            .select_related('cobro', 'turno')[:15]
        )
        cant_extracciones_cg = ExtraccionCajaGrande.objects.count()

        return render(request, 'cobranzas/caja_grande.html', {
            'total_recaudado':          total_recaudado,
            'total_depositado':         total_depositado,
            'total_extracciones':       total_extracciones,
            'pendiente':                pendiente,
            'cant_cierres':             cant_cierres,
            'cant_depositos':           cant_depositos,
            'depositos_pf':             depositos_pf,
            'depositos_rp':             depositos_rp,
            'depositos_wu':             depositos_wu,
            'ultimos_cierres':          ultimos_cierres,
            'extracciones_caja_grande': extracciones_caja_grande,
            'cant_extracciones_cg':     cant_extracciones_cg,
        })


# ─────────────────────────────────────────────────────────────
# AJAX: estado de caja grande
# ─────────────────────────────────────────────────────────────

class EstadoCajaGrandeAjax(LoginRequiredMixin, View):
    def get(self, request):
        total = get_total_caja_grande()
        dep   = get_total_depositado()
        ext   = get_total_extracciones()
        return JsonResponse({
            'total_recaudado':    float(total),
            'total_depositado':   float(dep),
            'total_extracciones': float(ext),
            'pendiente':          float(total - dep - ext),
        })