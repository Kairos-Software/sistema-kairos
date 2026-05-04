"""
views_cobros.py
Vistas del módulo de cobros.
CAMBIO: ConfirmarCobroAjax ahora requiere un turno abierto y
        asocia el cobro al turno activo.
NUEVO:  EditarCobroAjax permite corregir un cobro ya cerrado
        (ítems, pagos, fecha, observaciones) sin romper balances.
"""
import re
import json
from datetime import date
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.db import transaction
from django.db.models import Q, Sum

from .models import Servicio, Cobro, ItemCobro, PagoCobro, Turno
from .views_caja import get_turno_abierto


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
# HELPER FILTROS
# ═══════════════════════════════════════════════════════════

def _qs_por_filtros(filtros: dict):
    qs = Cobro.objects.filter(estado=Cobro.ESTADO_CERRADO)

    desde     = (filtros.get('desde')     or '').strip()
    hasta     = (filtros.get('hasta')     or '').strip()
    usuario   = (filtros.get('usuario')   or '').strip()
    metodo    = (filtros.get('metodo')    or '').strip()
    codigo    = (filtros.get('codigo')    or '').strip()
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
# HELPER PERMISOS — reemplazá con tu sistema cuando esté listo
# ═══════════════════════════════════════════════════════════

def puede_editar_cobros(user):
    """
    Retorna True si el usuario puede editar cobros.
    Cuando tengas tu sistema de permisos personalizado, reemplazá
    esta función. Ejemplo:
        return user.perfil.tiene_permiso('editar_cobros') or user.is_superuser
    """
    return user.is_staff or user.is_superuser


# ═══════════════════════════════════════════════════════════
# VISTAS PRINCIPALES
# ═══════════════════════════════════════════════════════════

class GestionCobrosView(LoginRequiredMixin, View):
    def get(self, request):
        turno = get_turno_abierto()
        return render(request, 'cobranzas/gestion_cobros.html', {
            'turno_abierto': turno,
        })


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
        # ── Verificar turno abierto ──────────────────────────
        turno = get_turno_abierto()
        if not turno:
            return JsonResponse({
                'error': 'No hay caja abierta. Abrí la caja antes de registrar cobros.',
                'sin_turno': True,
            }, status=400)

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
                turno=turno,
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
            'turno_numero':      turno.numero,
        })


class HistorialCobrosView(LoginRequiredMixin, View):
    def get(self, request):
        cobros = (
            Cobro.objects
            .filter(estado=Cobro.ESTADO_CERRADO)
            .select_related('creado_por', 'turno')
            .prefetch_related('items__servicio', 'pagos')
        )

        desde = request.GET.get('desde', '').strip()
        hasta = request.GET.get('hasta', '').strip()
        if desde:
            cobros = cobros.filter(fecha_cierre__date__gte=desde)
        if hasta:
            cobros = cobros.filter(fecha_cierre__date__lte=hasta)

        return render(request, 'cobranzas/historial_cobros.html', {
            'cobros':          cobros[:500],
            'desde':           desde,
            'hasta':           hasta,
            'metodos_choices': PagoCobro.METODOS,
        })


# ═══════════════════════════════════════════════════════════
# EDICIÓN DE COBROS
# ═══════════════════════════════════════════════════════════

class EditarCobroAjax(LoginRequiredMixin, View):
    """
    Edita un cobro ya cerrado reemplazando sus ItemCobro y PagoCobro.

    - El Cobro en sí (turno, creado_por, estado) NO se toca.
    - Si se envía fecha_cierre, se actualiza.
    - Los totales de caja se recalculan solos porque total_general(),
      total_boletas() y total_adicionales() son métodos calculados
      sobre los ítems y pagos relacionados, no campos guardados.

    Payload POST JSON:
    {
        "items": [
            {
                "servicio_id":     <int>,
                "monto_servicio":  <float>,
                "monto_adicional": <float>,
                "canal":           "pagofacil" | "rapipago" | "otro"
            }
        ],
        "pagos": [
            {
                "metodo": "efectivo" | "transferencia" | "debito" | "credito" | "qr",
                "monto":  <float>
            }
        ],
        "observaciones": <str>,
        "fecha_cierre":  <str>  "YYYY-MM-DDTHH:MM"  (null = no cambiar)
    }
    """

    def post(self, request, cobro_id):
        # ── Permiso ───────────────────────────────────────────────────────────
        if not puede_editar_cobros(request.user):
            return JsonResponse(
                {'error': 'No tenés permiso para editar cobros.'},
                status=403,
            )

        # ── Cobro ─────────────────────────────────────────────────────────────
        cobro = get_object_or_404(Cobro, pk=cobro_id, estado=Cobro.ESTADO_CERRADO)

        # ── Parse body ────────────────────────────────────────────────────────
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        items_data    = data.get('items', [])
        pagos_data    = data.get('pagos', [])
        observaciones = data.get('observaciones', '').strip()
        fecha_raw     = (data.get('fecha_cierre') or '').strip()

        # ── Validaciones básicas ──────────────────────────────────────────────
        if not items_data:
            return JsonResponse({'error': 'El cobro debe tener al menos un ítem.'}, status=400)
        if not pagos_data:
            return JsonResponse({'error': 'Debe registrar al menos un método de pago.'}, status=400)

        total_items = sum(
            float(i.get('monto_servicio', 0)) + float(i.get('monto_adicional', 0))
            for i in items_data
        )
        total_pagos = sum(float(p.get('monto', 0)) for p in pagos_data)

        if round(total_pagos, 2) < round(total_items, 2):
            return JsonResponse({
                'error': (
                    f'Los pagos (${total_pagos:,.2f}) no cubren el total '
                    f'(${total_items:,.2f}).'
                )
            }, status=400)

        # ── Validar y parsear fecha ───────────────────────────────────────────
        nueva_fecha = None
        if fecha_raw:
            nueva_fecha = parse_datetime(fecha_raw)
            if nueva_fecha is None:
                return JsonResponse(
                    {'error': 'Formato de fecha inválido. Usá YYYY-MM-DDTHH:MM.'},
                    status=400,
                )
            if timezone.is_naive(nueva_fecha):
                nueva_fecha = timezone.make_aware(nueva_fecha)

        # ── Transacción: reemplazar ítems y pagos ─────────────────────────────
        with transaction.atomic():
            # Borrar todo lo anterior
            cobro.items.all().delete()
            cobro.pagos.all().delete()

            # Insertar nuevos ítems
            for orden, item in enumerate(items_data):
                servicio = get_object_or_404(Servicio, pk=item['servicio_id'], activo=True)
                ItemCobro.objects.create(
                    cobro=cobro,
                    servicio=servicio,
                    monto_servicio=float(item.get('monto_servicio', 0)),
                    monto_adicional=float(item.get('monto_adicional', 0)),
                    canal=item.get('canal', ItemCobro.CANAL_PAGOFACIL),
                    orden=orden,
                )

            # Insertar nuevos pagos
            for pago in pagos_data:
                monto_pago = float(pago.get('monto', 0))
                if monto_pago > 0:
                    PagoCobro.objects.create(
                        cobro=cobro,
                        metodo=pago['metodo'],
                        monto=monto_pago,
                    )

            # Actualizar campos del cobro
            campos_a_guardar = ['observaciones']
            cobro.observaciones = observaciones
            if nueva_fecha:
                cobro.fecha_cierre = nueva_fecha
                campos_a_guardar.append('fecha_cierre')
            cobro.save(update_fields=campos_a_guardar)

        # ── Respuesta ─────────────────────────────────────────────────────────
        totales_por_metodo = {
            p.get_metodo_display(): float(p.monto)
            for p in cobro.pagos.all()
        }
        return JsonResponse({
            'success':           True,
            'cobro_id':          cobro.pk,
            'total_general':     float(cobro.total_general()),
            'total_boletas':     float(cobro.total_boletas()),
            'total_adicionales': float(cobro.total_adicionales()),
            'pagos':             totales_por_metodo,
            'fecha':             cobro.fecha_cierre.strftime('%d/%m/%Y %H:%M'),
        })


# ═══════════════════════════════════════════════════════════
# ELIMINACIÓN DE COBROS
# ═══════════════════════════════════════════════════════════

class EliminarCobrosAjax(LoginRequiredMixin, View):
    def post(self, request):
        if not (request.user.is_staff or request.user.is_superuser):
            return JsonResponse({'error': 'Solo administradores pueden eliminar cobros.'}, status=403)

        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido'}, status=400)

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