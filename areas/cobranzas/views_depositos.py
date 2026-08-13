"""
views_depositos.py
Vistas para el módulo de Depósitos Bancarios.
"""
import json
from decimal import Decimal, InvalidOperation

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Sum
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views import View
from django.db import transaction
from django.utils.dateparse import parse_datetime
from .models import DepositoBancario, DepositoTicket
from .views_recaudaciones import _totales_por_entidad


class DepositosView(LoginRequiredMixin, View):
    def get(self, request):
        entidad = request.GET.get('entidad', DepositoBancario.ENTIDAD_PAGOFACIL)
        if entidad not in (DepositoBancario.ENTIDAD_PAGOFACIL, DepositoBancario.ENTIDAD_RAPIPAGO):
            entidad = DepositoBancario.ENTIDAD_PAGOFACIL

        ultimos = (
            DepositoBancario.objects
            .filter(entidad=entidad)
            .select_related('realizado_por', 'ticket')[:10]
        )

        total_pf = (
            DepositoBancario.objects.filter(entidad=DepositoBancario.ENTIDAD_PAGOFACIL)
            .aggregate(t=Sum('monto'))['t'] or Decimal('0')
        )
        total_rp = (
            DepositoBancario.objects.filter(entidad=DepositoBancario.ENTIDAD_RAPIPAGO)
            .aggregate(t=Sum('monto'))['t'] or Decimal('0')
        )
        cant_pf = DepositoBancario.objects.filter(entidad=DepositoBancario.ENTIDAD_PAGOFACIL).count()
        cant_rp = DepositoBancario.objects.filter(entidad=DepositoBancario.ENTIDAD_RAPIPAGO).count()

        return render(request, 'cobranzas/depositos.html', {
            'entidad':       entidad,
            'entidad_label': 'PagoFácil' if entidad == DepositoBancario.ENTIDAD_PAGOFACIL else 'RapiPago',
            'ultimos':       ultimos,
            'total_pf':      total_pf,
            'total_rp':      total_rp,
            'cant_pf':       cant_pf,
            'cant_rp':       cant_rp,
            'ENTIDAD_PF':    DepositoBancario.ENTIDAD_PAGOFACIL,
            'ENTIDAD_RP':    DepositoBancario.ENTIDAD_RAPIPAGO,
            'hoy':           timezone.localdate(),
        })


class RegistrarDepositoAjax(LoginRequiredMixin, View):
    raise_exception = True  # Devuelve 403 JSON-friendly en vez de redirect 302

    def post(self, request):
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        entidad = data.get('entidad', '').strip()
        if entidad not in (DepositoBancario.ENTIDAD_PAGOFACIL, DepositoBancario.ENTIDAD_RAPIPAGO):
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

        tipo_deposito = data.get('tipo_deposito', '').strip()
        if tipo_deposito and tipo_deposito not in dict(DepositoBancario.TIPOS_DEPOSITO):
            return JsonResponse({'error': 'Tipo de depósito inválido.'}, status=400)

        numero_comprobante = data.get('numero_comprobante', '').strip()
        observaciones      = data.get('observaciones', '').strip()

        try:
            with transaction.atomic():
                # Pendiente ANTES de este depósito → así 'diferencia' refleja
                # sobrante/faltante de este depósito puntual, igual que en
                # ModDepositos.bas::RegistrarRecaudacion del Excel de referencia.
                pendiente_al_momento = _totales_por_entidad(entidad)['pendiente']
                diferencia = monto - pendiente_al_momento

                deposito = DepositoBancario.objects.create(
                    entidad=entidad,
                    fecha=fecha,
                    tipo_deposito=tipo_deposito,
                    monto=monto,
                    numero_comprobante=numero_comprobante,
                    diferencia=diferencia,
                    observaciones=observaciones,
                    realizado_por=request.user,
                )
        except Exception as e:
            import traceback
            traceback.print_exc()
            return JsonResponse({'error': f'Error al guardar: {e}'}, status=500)

        nuevo_total = (
            DepositoBancario.objects.filter(entidad=entidad)
            .aggregate(t=Sum('monto'))['t'] or Decimal('0')
        )

        fecha_display = deposito.fecha.strftime('%d/%m/%Y')

        try:
            realizado_por_str = request.user.get_full_name() or request.user.username
        except Exception:
            realizado_por_str = str(request.user.pk)

        return JsonResponse({
            'success':            True,
            'deposito_id':        deposito.pk,
            'entidad':            entidad,
            'entidad_label':      deposito.get_entidad_display(),
            'fecha':              fecha_display,
            'tipo_deposito':      deposito.tipo_deposito,
            'tipo_deposito_label': deposito.get_tipo_deposito_display() if deposito.tipo_deposito else '',
            'monto':              float(deposito.monto),
            'numero_comprobante': deposito.numero_comprobante or '',
            'diferencia':         float(deposito.diferencia) if deposito.diferencia is not None else None,
            'observaciones':      deposito.observaciones or '',
            'realizado_por':      realizado_por_str,
            'nuevo_total':        float(nuevo_total),
        })


class HistorialDepositosView(LoginRequiredMixin, View):
    def get(self, request):
        desde         = request.GET.get('desde',   '').strip()
        hasta         = request.GET.get('hasta',   '').strip()
        entidad       = request.GET.get('entidad', '').strip()
        tipo_deposito = request.GET.get('tipo_deposito', '').strip()

        qs = DepositoBancario.objects.select_related('realizado_por', 'ticket').all()

        if desde:
            qs = qs.filter(fecha__gte=desde)
        if hasta:
            qs = qs.filter(fecha__lte=hasta)
        if entidad in (DepositoBancario.ENTIDAD_PAGOFACIL, DepositoBancario.ENTIDAD_RAPIPAGO):
            qs = qs.filter(entidad=entidad)
        if tipo_deposito in dict(DepositoBancario.TIPOS_DEPOSITO):
            qs = qs.filter(tipo_deposito=tipo_deposito)

        total_filtrado    = qs.aggregate(t=Sum('monto'))['t'] or Decimal('0')
        total_pf_filtrado = (
            qs.filter(entidad=DepositoBancario.ENTIDAD_PAGOFACIL)
            .aggregate(t=Sum('monto'))['t'] or Decimal('0')
        )
        total_rp_filtrado = (
            qs.filter(entidad=DepositoBancario.ENTIDAD_RAPIPAGO)
            .aggregate(t=Sum('monto'))['t'] or Decimal('0')
        )

        return render(request, 'cobranzas/historial_depositos.html', {
            'depositos':          qs[:500],
            'desde':              desde,
            'hasta':              hasta,
            'entidad':            entidad,
            'tipo_deposito':      tipo_deposito,
            'total_filtrado':     total_filtrado,
            'total_pf_filtrado':  total_pf_filtrado,
            'total_rp_filtrado':  total_rp_filtrado,
            'ENTIDAD_PF':         DepositoBancario.ENTIDAD_PAGOFACIL,
            'ENTIDAD_RP':         DepositoBancario.ENTIDAD_RAPIPAGO,
            'TIPOS_DEPOSITO':     DepositoBancario.TIPOS_DEPOSITO,
        })
    

class TicketDepositoAjax(LoginRequiredMixin, View):
    """Ver/editar el comprobante (ticket) asociado a un DepositoBancario."""

    CAMPOS_TEXTO = [
        'numero_operacion', 'banco', 'titular_nombre', 'titular_cuit',
        'cuenta_origen', 'destinatario', 'cuenta_destino', 'sucursal',
        'concepto', 'estado', 'observaciones',
    ]

    def get(self, request):
        deposito_id = request.GET.get('deposito_id')
        deposito = get_object_or_404(DepositoBancario, pk=deposito_id)
        ticket = getattr(deposito, 'ticket', None)

        if ticket is None:
            return JsonResponse({'existe': False})

        data = {campo: getattr(ticket, campo) for campo in self.CAMPOS_TEXTO}
        fecha_hora_local = (
            timezone.localtime(ticket.fecha_hora_ticket) if ticket.fecha_hora_ticket else None
        )
        data.update({
            'existe':            True,
            'fecha_hora_ticket': fecha_hora_local.isoformat() if fecha_hora_local else '',
            'monto_ticket':      float(ticket.monto_ticket) if ticket.monto_ticket is not None else None,
            'imagen_url':        ticket.imagen.url if ticket.imagen else '',
        })
        return JsonResponse(data)

    def post(self, request):
        deposito_id = request.POST.get('deposito_id')
        deposito = get_object_or_404(DepositoBancario, pk=deposito_id)

        ticket, _ = DepositoTicket.objects.get_or_create(deposito=deposito)

        for campo in self.CAMPOS_TEXTO:
            setattr(ticket, campo, request.POST.get(campo, '').strip())

        fecha_hora_raw = request.POST.get('fecha_hora_ticket', '').strip()
        fecha_hora_parsed = parse_datetime(fecha_hora_raw) if fecha_hora_raw else None
        if fecha_hora_parsed and timezone.is_naive(fecha_hora_parsed):
            # El <input type="datetime-local"> manda un valor sin timezone,
            # que representa la hora local (America/Argentina/Buenos_Aires).
            fecha_hora_parsed = timezone.make_aware(fecha_hora_parsed)
        ticket.fecha_hora_ticket = fecha_hora_parsed

        monto_raw = request.POST.get('monto_ticket', '').strip()
        if monto_raw:
            try:
                ticket.monto_ticket = Decimal(monto_raw)
            except InvalidOperation:
                return JsonResponse({'error': 'El monto del ticket es inválido.'}, status=400)
        else:
            ticket.monto_ticket = None

        if 'imagen' in request.FILES:
            ticket.imagen = request.FILES['imagen']

        ticket.cargado_por = request.user
        ticket.save()

        return JsonResponse({
            'success':     True,
            'deposito_id': deposito.pk,
            'imagen_url':  ticket.imagen.url if ticket.imagen else '',
        })


class EliminarDepositosAjax(LoginRequiredMixin, View):
    """Elimina uno o varios DepositoBancario por ID. Solo staff/superuser."""
    def post(self, request):
        if not (request.user.is_staff or request.user.is_superuser):
            return JsonResponse({'error': 'Solo administradores pueden eliminar depósitos.'}, status=403)
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
            eliminados, _ = DepositoBancario.objects.filter(pk__in=ids).delete()
 
        return JsonResponse({'success': True, 'eliminados': eliminados})