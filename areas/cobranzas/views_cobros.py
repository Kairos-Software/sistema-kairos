import re
import json
from datetime import date
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View
from django.utils import timezone
from django.db import transaction
from django.db.models import Q, Sum

from .models import Servicio, Cobro, ItemCobro, PagoCobro


# ═══════════════════════════════════════════════════════════
# LÓGICA DE RANGOS
# ═══════════════════════════════════════════════════════════

_PATRONES_RANGO = [
    re.compile(r'RANGO:\s*(\d+)\s*[-–]\s*(\d+)', re.IGNORECASE),
    re.compile(r'desde\s+(\d+)\s+hasta\s+(\d+)', re.IGNORECASE),
    re.compile(r'\bde\s+(\d+)\s+a\s+(\d+)\b', re.IGNORECASE),
    re.compile(r'entre\s+(\d+)\s+y\s+(\d+)', re.IGNORECASE),
    re.compile(r'(?<!\w)(\d+)\s*[-–]\s*(\d+)(?!\w)'),
]


def extraer_rango(descripcion: str):
    for patron in _PATRONES_RANGO:
        m = patron.search(descripcion)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            return (min(a, b), max(a, b))
    return None


def resolver_adicional(prefijo: str, valor_boleta: float):
    prefijo = prefijo.strip().upper()
    candidatos = list(Servicio.objects.filter(activo=True, codigo__istartswith=prefijo))
    rangos_coinciden, fijos = [], []
    for s in candidatos:
        rango = extraer_rango(s.descripcion)
        if rango is None:
            fijos.append(s)
        else:
            lo, hi = rango
            if lo <= valor_boleta <= hi:
                rangos_coinciden.append(s)
    if len(rangos_coinciden) == 1:
        return {'servicio': rangos_coinciden[0], 'tipo': 'rango'}
    if len(rangos_coinciden) > 1:
        return {'servicio': None, 'tipo': 'conflicto', 'conflicto': rangos_coinciden}
    if len(fijos) == 1:
        return {'servicio': fijos[0], 'tipo': 'fijo'}
    if len(fijos) > 1:
        return {'servicio': None, 'tipo': 'conflicto', 'conflicto': fijos}
    return {'servicio': None, 'tipo': 'no_encontrado'}


# ═══════════════════════════════════════════════════════════
# HELPER: armar queryset de cobros desde un dict de filtros
# Usado tanto para previsualizar como para eliminar por filtros.
# ═══════════════════════════════════════════════════════════

def _qs_por_filtros(filtros: dict):
    """
    Recibe un dict con claves opcionales:
      desde, hasta, usuario, metodo, codigo, monto_min, monto_max
    Retorna un QuerySet de Cobro filtrado.
    """
    qs = Cobro.objects.filter(estado=Cobro.ESTADO_CERRADO)

    desde = (filtros.get('desde') or '').strip()
    hasta = (filtros.get('hasta') or '').strip()
    usuario  = (filtros.get('usuario')  or '').strip()
    metodo   = (filtros.get('metodo')   or '').strip()
    codigo   = (filtros.get('codigo')   or '').strip()
    monto_min = (filtros.get('monto_min') or '').strip()
    monto_max = (filtros.get('monto_max') or '').strip()

    if desde:
        qs = qs.filter(fecha_cierre__date__gte=desde)
    if hasta:
        qs = qs.filter(fecha_cierre__date__lte=hasta)
    if usuario:
        qs = qs.filter(creado_por__username__icontains=usuario)
    if metodo:
        qs = qs.filter(pagos__metodo=metodo)
    if codigo:
        qs = qs.filter(items__servicio__codigo__icontains=codigo)
    if monto_min:
        try:
            qs = qs.filter(items__monto_servicio__gte=float(monto_min))
        except ValueError:
            pass
    if monto_max:
        try:
            qs = qs.filter(items__monto_servicio__lte=float(monto_max))
        except ValueError:
            pass

    return qs.distinct()


# ═══════════════════════════════════════════════════════════
# VISTAS PRINCIPALES
# ═══════════════════════════════════════════════════════════

class GestionCobrosView(LoginRequiredMixin, View):
    def get(self, request):
        return render(request, 'cobranzas/gestion_cobros.html')


class BuscarServicioAjax(LoginRequiredMixin, View):
    def get(self, request):
        prefijo   = request.GET.get('prefijo', '').strip()
        valor_raw = request.GET.get('valor', '').strip()

        if prefijo and valor_raw:
            try:
                valor = float(valor_raw.replace(',', '.'))
            except ValueError:
                return JsonResponse({'error': 'El valor de boleta debe ser un número.'}, status=400)

            resultado = resolver_adicional(prefijo, valor)

            if resultado['tipo'] == 'no_encontrado':
                return JsonResponse({
                    'encontrado': False,
                    'mensaje': f'No se encontró ningún servicio activo con prefijo "{prefijo.upper()}" '
                               f'que cubra el valor ${valor:,.2f}.',
                })
            if resultado['tipo'] == 'conflicto':
                codigos = ', '.join(s.codigo for s in resultado['conflicto'])
                return JsonResponse({
                    'encontrado': False,
                    'mensaje': f'Conflicto: varios servicios ({codigos}) coinciden con ese valor. '
                               f'Revisá los rangos cargados.',
                })
            s = resultado['servicio']
            return JsonResponse({
                'encontrado': True,
                'tipo': resultado['tipo'],
                'servicio': {
                    'id':          s.pk,
                    'codigo':      s.codigo,
                    'descripcion': s.descripcion,
                    'monto':       str(s.monto),
                    'proveedor':   s.proveedor,
                },
            })

        q = request.GET.get('q', '').strip()
        if not q:
            return JsonResponse({'servicios': []})

        qs = Servicio.objects.filter(activo=True)
        try:
            monto_val = float(q.replace(',', '.'))
            qs = qs.filter(
                Q(codigo__icontains=q) | Q(descripcion__icontains=q) |
                Q(proveedor__icontains=q) | Q(monto=monto_val)
            )
        except ValueError:
            qs = qs.filter(
                Q(codigo__icontains=q) | Q(descripcion__icontains=q) | Q(proveedor__icontains=q)
            )
        servicios = list(qs.values('id', 'codigo', 'descripcion', 'monto', 'proveedor')[:20])
        return JsonResponse({'servicios': servicios})


class ConfirmarCobroAjax(LoginRequiredMixin, View):
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
                    monto_servicio=item.get('monto_servicio', 0),
                    monto_adicional=item.get('monto_adicional', 0),
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
            'success':           True,
            'cobro_id':          cobro.pk,
            'total_general':     float(cobro.total_general()),
            'total_boletas':     float(cobro.total_boletas()),
            'total_adicionales': float(cobro.total_adicionales()),
            'pagos':             totales_por_metodo,
            'fecha':             cobro.fecha_cierre.strftime('%d/%m/%Y %H:%M'),
        })


class HistorialCobrosView(LoginRequiredMixin, View):
    """Lista de cobros cerrados. Filtro de búsqueda solo por fecha."""
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
            'cobros':           cobros[:500],
            'desde':            desde,
            'hasta':            hasta,
            'metodos_choices':  PagoCobro.METODOS,
        })


# ═══════════════════════════════════════════════════════════
# ELIMINACIÓN DE COBROS
# ═══════════════════════════════════════════════════════════

class EliminarCobrosAjax(LoginRequiredMixin, View):
    """
    Elimina cobros. Acepta dos modos en el body JSON:

    Modo 1 — por IDs directos:
        { "ids": [1, 2, 3] }

    Modo 2 — por filtros (viene del modal "Eliminar registros"):
        { "filtros": { "desde": "2025-01-01", "hasta": "2025-01-31", ... } }

    Al eliminar un Cobro en cascade se eliminan sus ItemCobro y PagoCobro,
    liberando las FK protegidas en Servicio.
    """
    def post(self, request):
        if not (request.user.is_staff or request.user.is_superuser):
            return JsonResponse({'error': 'Solo administradores pueden eliminar cobros.'}, status=403)

        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido'}, status=400)

        # ── Modo 1: por IDs ──────────────────────────────────
        if 'ids' in data:
            ids = data['ids']
            if not ids:
                return JsonResponse({'error': 'No se recibieron IDs.'}, status=400)
            try:
                ids = [int(i) for i in ids]
            except (ValueError, TypeError):
                return JsonResponse({'error': 'IDs inválidos.'}, status=400)

            with transaction.atomic():
                eliminados, _ = Cobro.objects.filter(pk__in=ids).delete()
            return JsonResponse({'success': True, 'eliminados': eliminados})

        # ── Modo 2: por filtros ──────────────────────────────
        if 'filtros' in data:
            filtros = data['filtros']
            if not isinstance(filtros, dict):
                return JsonResponse({'error': 'Filtros inválidos.'}, status=400)

            qs = _qs_por_filtros(filtros)
            total = qs.count()

            if total == 0:
                return JsonResponse({'error': 'Ningún cobro coincide con los criterios indicados.'}, status=400)

            with transaction.atomic():
                eliminados, _ = qs.delete()
            return JsonResponse({'success': True, 'eliminados': eliminados})

        return JsonResponse({'error': 'Parámetros inválidos. Enviá "ids" o "filtros".'}, status=400)


class PrevisualizarElimFiltroAjax(LoginRequiredMixin, View):
    """
    Cuenta cuántos cobros serían eliminados con los filtros dados.
    No borra nada — solo informa el total para que el usuario confirme.

    POST body JSON: mismo dict de filtros que EliminarCobrosAjax (modo filtros).
    Respuesta: { "count": N }
    """
    def post(self, request):
        if not (request.user.is_staff or request.user.is_superuser):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            filtros = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido'}, status=400)

        if not isinstance(filtros, dict):
            return JsonResponse({'error': 'Formato inválido.'}, status=400)

        count = _qs_por_filtros(filtros).count()
        return JsonResponse({'count': count})


class LimpiezaAutomaticaAjax(LoginRequiredMixin, View):
    """
    Elimina todos los cobros cerrados del mes anterior al de ejecución.
    Solo disponible a partir del día 20 del mes.
    Solo staff/superuser.
    """
    def post(self, request):
        if not (request.user.is_staff or request.user.is_superuser):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        hoy = date.today()
        if hoy.day < 20:
            return JsonResponse({
                'error': f'La limpieza automática se activa a partir del día 20. Hoy es {hoy.day}.'
            }, status=400)

        if hoy.month == 1:
            mes_anterior  = 12
            anio_anterior = hoy.year - 1
        else:
            mes_anterior  = hoy.month - 1
            anio_anterior = hoy.year

        with transaction.atomic():
            eliminados, _ = Cobro.objects.filter(
                estado=Cobro.ESTADO_CERRADO,
                fecha_cierre__year=anio_anterior,
                fecha_cierre__month=mes_anterior,
            ).delete()

        mes_nombre = [
            '', 'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
            'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'
        ][mes_anterior]

        return JsonResponse({
            'success':    True,
            'eliminados': eliminados,
            'periodo':    f'{mes_nombre} {anio_anterior}',
        })