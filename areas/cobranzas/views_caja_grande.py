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

from .models import CierreDiario, DepositoBancario


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


# ─────────────────────────────────────────────────────────────
# VISTA: Caja Grande
# ─────────────────────────────────────────────────────────────

class CajaGrandeView(LoginRequiredMixin, View):
    def get(self, request):
        total_recaudado  = get_total_caja_grande()
        total_depositado = get_total_depositado()
        pendiente        = total_recaudado - total_depositado

        cant_cierres   = CierreDiario.objects.count()
        cant_depositos = DepositoBancario.objects.count()

        depositos_pf = (
            DepositoBancario.objects
            .filter(entidad=DepositoBancario.ENTIDAD_PAGOFACIL)
            .aggregate(t=Sum('monto'))['t'] or Decimal('0')
        )
        depositos_rp = (
            DepositoBancario.objects
            .filter(entidad=DepositoBancario.ENTIDAD_RAPIPAGO)
            .aggregate(t=Sum('monto'))['t'] or Decimal('0')
        )

        ultimos_cierres = (
            CierreDiario.objects
            .select_related('realizado_por')[:8]
        )

        return render(request, 'cobranzas/caja_grande.html', {
            'total_recaudado':  total_recaudado,
            'total_depositado': total_depositado,
            'pendiente':        pendiente,
            'cant_cierres':     cant_cierres,
            'cant_depositos':   cant_depositos,
            'depositos_pf':     depositos_pf,
            'depositos_rp':     depositos_rp,
            'ultimos_cierres':  ultimos_cierres,
        })


# ─────────────────────────────────────────────────────────────
# AJAX: estado de caja grande
# ─────────────────────────────────────────────────────────────

class EstadoCajaGrandeAjax(LoginRequiredMixin, View):
    def get(self, request):
        total = get_total_caja_grande()
        dep   = get_total_depositado()
        return JsonResponse({
            'total_recaudado':  float(total),
            'total_depositado': float(dep),
            'pendiente':        float(total - dep),
        })