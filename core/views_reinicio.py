# core/views_reinicio.py
#
# "Reiniciar sistema": borra todos los datos transaccionales de
# cobranzas (turnos, cobros, depósitos, recaudaciones, cierres diarios,
# ganancias) para dejar la base lista para empezar a usarse de verdad en
# producción, sin tocar usuarios, clientes, el catálogo de servicios
# (Servicio/PrefijoServicio) ni nada del área de software.
#
# Solo superusuarios. Requiere que el usuario escriba la frase de
# confirmación exacta en el body del POST — no alcanza con un clic.
import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views import View

from areas.cobranzas.models import (
    AjusteSaldoFavor,
    CierreDiario,
    Cobro,
    DepositoBancario,
    GastoGanancia,
    RecaudacionDiaria,
    Turno,
)

FRASE_CONFIRMACION = 'REINICIAR'

# Etiqueta legible → queryset. Orden relevante: Cobro.turno es PROTECT,
# así que los cobros (y sus items/pagos, que cascadean solos) tienen que
# borrarse antes que los turnos.
_MODELOS_A_BORRAR = [
    ('Cobros (boletas, ítems y pagos)', Cobro),
    ('Turnos de caja (y retiros)',      Turno),
    ('Cierres diarios',                 CierreDiario),
    ('Depósitos bancarios (y tickets)', DepositoBancario),
    ('Recaudaciones diarias',           RecaudacionDiaria),
    ('Gastos de ganancias',             GastoGanancia),
    ('Usos de saldo a favor',           AjusteSaldoFavor),
]


def _conteos():
    return [(etiqueta, modelo.objects.count()) for etiqueta, modelo in _MODELOS_A_BORRAR]


class ReinicioSistemaView(LoginRequiredMixin, View):
    def get(self, request):
        if not request.user.is_superuser:
            return redirect('core:home')

        return render(request, 'core/reinicio.html', {
            'conteos':             _conteos(),
            'frase_confirmacion':  FRASE_CONFIRMACION,
        })


class EjecutarReinicioAjax(LoginRequiredMixin, View):
    def post(self, request):
        if not request.user.is_superuser:
            return JsonResponse({'error': 'Solo superusuarios pueden ejecutar esta acción.'}, status=403)

        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        if data.get('confirmacion', '').strip() != FRASE_CONFIRMACION:
            return JsonResponse({
                'error': f'Escribí exactamente "{FRASE_CONFIRMACION}" para confirmar.'
            }, status=400)

        conteos_antes = dict(_conteos())

        with transaction.atomic():
            Cobro.objects.all().delete()
            Turno.objects.all().delete()
            CierreDiario.objects.all().delete()
            DepositoBancario.objects.all().delete()
            RecaudacionDiaria.objects.all().delete()
            GastoGanancia.objects.all().delete()
            AjusteSaldoFavor.objects.all().delete()

        return JsonResponse({'success': True, 'conteos_eliminados': conteos_antes})
