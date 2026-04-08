from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View
from django.utils import timezone
from django.db import transaction
from django.db.models import Q
import json

from .models import Servicio, Cobro, ItemCobro, PagoCobro


class GestionCobrosView(LoginRequiredMixin, View):
    """Pantalla principal del carrito de cobros."""
    def get(self, request):
        return render(request, 'cobranzas/gestion_cobros.html')


class BuscarServicioAjax(LoginRequiredMixin, View):
    """Búsqueda de servicios activos para el buscador del carrito."""
    def get(self, request):
        q = request.GET.get('q', '').strip()
        if not q:
            return JsonResponse({'servicios': []})

        qs = Servicio.objects.filter(activo=True)

        try:
            monto_val = float(q.replace(',', '.'))
            qs = qs.filter(
                Q(codigo__icontains=q) |
                Q(descripcion__icontains=q) |
                Q(proveedor__icontains=q) |
                Q(monto=monto_val)
            )
        except ValueError:
            qs = qs.filter(
                Q(codigo__icontains=q) |
                Q(descripcion__icontains=q) |
                Q(proveedor__icontains=q)
            )

        # Devolvemos "monto" que en el modelo = nuestro adicional fijo
        servicios = list(qs.values('id', 'codigo', 'descripcion', 'monto', 'proveedor')[:20])
        return JsonResponse({'servicios': servicios})


class ConfirmarCobroAjax(LoginRequiredMixin, View):
    """
    Recibe el payload del carrito y lo guarda en la base de datos.

    Nomenclatura en el payload:
      monto_servicio  → importe de la factura (cargado por el usuario)
      monto_adicional → adicional fijo del servicio (nuestra ganancia)
    """
    def post(self, request):
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido'}, status=400)

        items_data    = data.get('items', [])
        pagos_data    = data.get('pagos', [])
        observaciones = data.get('observaciones', '').strip()

        if not items_data:
            return JsonResponse({'error': 'No hay ítems en el cobro.'}, status=400)
        if not pagos_data:
            return JsonResponse({'error': 'Debe registrar al menos un método de pago.'}, status=400)

        total_items = sum(
            float(i.get('monto_servicio', 0)) + float(i.get('monto_adicional', 0))
            for i in items_data
        )
        total_pagos = sum(float(p.get('monto', 0)) for p in pagos_data)

        if round(total_pagos, 2) < round(total_items, 2):
            return JsonResponse({
                'error': f'Los pagos (${total_pagos:,.2f}) no cubren el total (${total_items:,.2f}).'
            }, status=400)

        with transaction.atomic():
            cobro = Cobro.objects.create(
                estado=Cobro.ESTADO_CERRADO,
                fecha_cierre=timezone.now(),
                creado_por=request.user,
                observaciones=observaciones,
            )

            for orden, item in enumerate(items_data):
                servicio = get_object_or_404(Servicio, pk=item['servicio_id'], activo=True)
                ItemCobro.objects.create(
                    cobro=cobro,
                    servicio=servicio,
                    monto_servicio=item.get('monto_servicio', 0),   # factura del cliente
                    monto_adicional=item.get('monto_adicional', 0), # nuestro adicional
                    canal=item.get('canal', ItemCobro.CANAL_PAGOFACIL),
                    orden=orden,
                )

            for pago in pagos_data:
                monto_pago = float(pago.get('monto', 0))
                if monto_pago > 0:
                    PagoCobro.objects.create(
                        cobro=cobro,
                        metodo=pago['metodo'],
                        monto=monto_pago,
                    )

        totales_por_metodo = {p.get_metodo_display(): float(p.monto) for p in cobro.pagos.all()}

        return JsonResponse({
            'success': True,
            'cobro_id': cobro.pk,
            'total_general': float(cobro.total_general()),
            'total_boletas': float(cobro.total_boletas()),
            'total_adicionales': float(cobro.total_adicionales()),
            'pagos': totales_por_metodo,
            'fecha': cobro.fecha_cierre.strftime('%d/%m/%Y %H:%M'),
        })


class HistorialCobrosView(LoginRequiredMixin, View):
    """Lista de cobros cerrados con filtro por fecha."""
    def get(self, request):
        cobros = (
            Cobro.objects
            .filter(estado=Cobro.ESTADO_CERRADO)
            .select_related('creado_por')
            .prefetch_related('items__servicio', 'pagos')
        )

        desde = request.GET.get('desde', '').strip()
        hasta = request.GET.get('hasta', '').strip()
        if desde:
            cobros = cobros.filter(fecha_cierre__date__gte=desde)
        if hasta:
            cobros = cobros.filter(fecha_cierre__date__lte=hasta)

        return render(request, 'cobranzas/historial_cobros.html', {
            'cobros': cobros[:200],
            'desde':  desde,
            'hasta':  hasta,
        })