"""
views_depositos.py
Vistas para el módulo de Depósitos Bancarios.
"""
import json
from decimal import Decimal, InvalidOperation

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Sum, Min, Max
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views import View
from django.db import transaction
from django.utils.dateparse import parse_datetime
from .models import DepositoBancario, DepositoTicket, RecaudacionDiaria, AjusteSaldoFavor
from .views_recaudaciones import (
    _totales_por_entidad, _ultima_diferencia, _recaudado_pendiente,
    ENTIDADES_VALIDAS,
)


def _periodo_pendiente(entidad: str):
    """Rango de fechas (min, max) de la recaudación todavía no cubierta, o None."""
    agregado = (
        RecaudacionDiaria.objects
        .filter(entidad=entidad, cubierta_por__isnull=True)
        .aggregate(desde=Min('fecha'), hasta=Max('fecha'))
    )
    if agregado['desde'] is None:
        return None
    return agregado['desde'], agregado['hasta']


def _marcar_tickets_cargados(depositos):
    """
    Adjunta a cada DepositoBancario un set `.tickets_cargados` con los
    `tipo` que ya tienen ticket cargado (requiere que el queryset venga
    con `.prefetch_related('tickets')` para no disparar N+1 queries).
    """
    depositos = list(depositos)
    for d in depositos:
        d.tickets_cargados = {t.tipo for t in d.tickets.all()}
    return depositos


class DepositosView(LoginRequiredMixin, View):
    def get(self, request):
        PF = DepositoBancario.ENTIDAD_PAGOFACIL
        RP = DepositoBancario.ENTIDAD_RAPIPAGO
        WU = DepositoBancario.ENTIDAD_WESTERN_UNION

        entidad = request.GET.get('entidad', PF)
        if entidad not in ENTIDADES_VALIDAS:
            entidad = PF

        ultimos = _marcar_tickets_cargados(
            DepositoBancario.objects
            .filter(entidad=entidad)
            .select_related('realizado_por')
            .prefetch_related('tickets')[:10]
        )

        def _cant(ent):
            return DepositoBancario.objects.filter(entidad=ent).count()
        cant_pf, cant_rp, cant_wu = _cant(PF), _cant(RP), _cant(WU)

        # Pendiente/a-favor de cada entidad, para el pill del selector (igual
        # que en recaudaciones.html) — 'pendiente' se mantiene con signo para
        # otros cálculos, pero en pantalla siempre se separa en dos valores
        # no-negativos (pendiente_mostrar / a_favor).
        tot_pf = _totales_por_entidad(PF)
        tot_rp = _totales_por_entidad(RP)
        tot_wu = _totales_por_entidad(WU)
        tot_por_entidad = {PF: tot_pf, RP: tot_rp, WU: tot_wu}

        # ── Mensajes clave (igual que FrmDeposito del Excel de referencia) ──
        # 'Neto a depositar' nunca debe mostrarse negativo: si ya se depositó
        # de más, lo que "falta depositar" es $0 (el sobrante se ve aparte en
        # 'Última diferencia').
        neto_a_depositar    = tot_por_entidad[entidad]['pendiente_mostrar']
        saldo_anterior      = _ultima_diferencia(entidad)
        recaudado_pendiente = _recaudado_pendiente(entidad)
        periodo             = _periodo_pendiente(entidad)

        usos_saldo = (
            AjusteSaldoFavor.objects
            .filter(entidad=entidad)
            .select_related('registrado_por')[:15]
        )

        return render(request, 'cobranzas/depositos.html', {
            'entidad':             entidad,
            'entidad_label':       dict(DepositoBancario.ENTIDADES).get(entidad, entidad),
            'ultimos':             ultimos,
            'cant_pf':             cant_pf,
            'cant_rp':             cant_rp,
            'cant_wu':             cant_wu,
            'tot_pf':              tot_pf,
            'tot_rp':              tot_rp,
            'tot_wu':              tot_wu,
            'neto_a_depositar':    neto_a_depositar,
            'saldo_anterior':      saldo_anterior,
            'recaudado_pendiente': recaudado_pendiente,
            'periodo_desde':       periodo[0] if periodo else None,
            'periodo_hasta':       periodo[1] if periodo else None,
            'usos_saldo':          usos_saldo,
            'ENTIDAD_PF':          PF,
            'ENTIDAD_RP':          RP,
            'ENTIDAD_WU':          WU,
            'hoy':                 timezone.localdate(),
        })


class PendientesRecaudacionAjax(LoginRequiredMixin, View):
    """
    GET ?entidad=pagofacil|rapipago|western_union
    Devuelve las recaudaciones sin cubrir de esa entidad, para el selector de
    días al registrar un depósito.
    """
    def get(self, request):
        entidad = request.GET.get('entidad', '').strip()
        if entidad not in ENTIDADES_VALIDAS:
            return JsonResponse({'error': 'Entidad inválida.'}, status=400)

        pendientes = (
            RecaudacionDiaria.objects
            .filter(entidad=entidad, cubierta_por__isnull=True)
            .order_by('fecha')
        )
        return JsonResponse({
            'pendientes': [
                {
                    'id':            r.pk,
                    'fecha':         str(r.fecha),
                    'fecha_display': r.fecha.strftime('%d/%m/%Y'),
                    'monto':         float(r.monto),
                }
                for r in pendientes
            ],
        })


class RegistrarDepositoAjax(LoginRequiredMixin, View):
    raise_exception = True  # Devuelve 403 JSON-friendly en vez de redirect 302

    def post(self, request):
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        entidad = data.get('entidad', '').strip()
        if entidad not in ENTIDADES_VALIDAS:
            return JsonResponse({'error': 'Entidad inválida.'}, status=400)

        fecha_raw = data.get('fecha', '').strip()
        if not fecha_raw:
            return JsonResponse({'error': 'La fecha es obligatoria.'}, status=400)
        fecha = parse_date(fecha_raw)
        if fecha is None:
            return JsonResponse({'error': 'Fecha inválida. Usá el formato AAAA-MM-DD.'}, status=400)
        if fecha > timezone.localdate():
            return JsonResponse({'error': 'La fecha no puede ser futura.'}, status=400)

        def _parse_componente(nombre):
            try:
                valor = Decimal(str(data.get(nombre, 0) or 0))
            except InvalidOperation:
                return None
            if valor < 0:
                return None
            return valor

        monto_efectivo_fisico  = _parse_componente('monto_efectivo_fisico')
        monto_ya_en_banco      = _parse_componente('monto_ya_en_banco')
        monto_saldo_plataforma = _parse_componente('monto_saldo_plataforma')
        if None in (monto_efectivo_fisico, monto_ya_en_banco, monto_saldo_plataforma):
            return JsonResponse({'error': 'Los montos deben ser números válidos, no negativos.'}, status=400)

        monto = monto_efectivo_fisico + monto_ya_en_banco + monto_saldo_plataforma
        if monto <= 0:
            return JsonResponse({'error': 'El monto total debe ser mayor a cero.'}, status=400)

        numero_comprobante = data.get('numero_comprobante', '').strip()
        observaciones      = data.get('observaciones', '').strip()

        try:
            recaudaciones_ids = [int(i) for i in data.get('recaudaciones_ids', [])]
        except (ValueError, TypeError):
            return JsonResponse({'error': 'IDs de recaudación inválidos.'}, status=400)

        try:
            with transaction.atomic():
                # Recaudaciones seleccionadas para este depósito: se valida
                # que sean de esta entidad y sigan sin cubrir (protege contra
                # dos personas depositando casi al mismo tiempo).
                seleccionadas = list(
                    RecaudacionDiaria.objects
                    .filter(pk__in=recaudaciones_ids, entidad=entidad, cubierta_por__isnull=True)
                )
                if len(seleccionadas) != len(set(recaudaciones_ids)):
                    return JsonResponse({
                        'error': 'Alguna recaudación seleccionada ya no está disponible '
                                 '(puede que otra persona ya la haya cubierto). Recargá la página.'
                    }, status=409)

                # Snapshot del cálculo ANTES de este depósito → 'diferencia'
                # (y el resto de los campos) reflejan el cálculo tal como
                # estaba en ese momento, igual que
                # ModDepositos.bas::RegistrarRecaudacion del Excel de
                # referencia, pero guardado para que el historial quede
                # auditable (no solo el resultado final).
                saldo_anterior_momento = _ultima_diferencia(entidad)  # None = sin depósito previo
                recaudado_pendiente_momento = sum((r.monto for r in seleccionadas), Decimal('0'))
                pendiente_al_momento = recaudado_pendiente_momento - (saldo_anterior_momento or Decimal('0'))
                neto_a_depositar_momento = max(pendiente_al_momento, Decimal('0'))
                diferencia = monto - pendiente_al_momento

                if seleccionadas:
                    periodo_desde_momento = min(r.fecha for r in seleccionadas)
                    periodo_hasta_momento = max(r.fecha for r in seleccionadas)
                else:
                    periodo_desde_momento = periodo_hasta_momento = None

                deposito = DepositoBancario.objects.create(
                    entidad=entidad,
                    fecha=fecha,
                    monto_efectivo_fisico=monto_efectivo_fisico,
                    monto_ya_en_banco=monto_ya_en_banco,
                    monto_saldo_plataforma=monto_saldo_plataforma,
                    monto=monto,
                    numero_comprobante=numero_comprobante,
                    diferencia=diferencia,
                    recaudado_pendiente_momento=recaudado_pendiente_momento,
                    saldo_anterior_momento=saldo_anterior_momento,
                    neto_a_depositar_momento=neto_a_depositar_momento,
                    periodo_desde_momento=periodo_desde_momento,
                    periodo_hasta_momento=periodo_hasta_momento,
                    observaciones=observaciones,
                    realizado_por=request.user,
                )

                RecaudacionDiaria.objects.filter(pk__in=[r.pk for r in seleccionadas]).update(
                    cubierta_por=deposito
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

        periodo_str = None
        if deposito.periodo_desde_momento:
            periodo_str = (
                f"{deposito.periodo_desde_momento.strftime('%d/%m/%Y')} al "
                f"{deposito.periodo_hasta_momento.strftime('%d/%m/%Y')}"
            )

        return JsonResponse({
            'success':            True,
            'deposito_id':        deposito.pk,
            'entidad':            entidad,
            'entidad_label':      deposito.get_entidad_display(),
            'fecha':              fecha_display,
            'monto_efectivo_fisico':  float(deposito.monto_efectivo_fisico),
            'monto_ya_en_banco':      float(deposito.monto_ya_en_banco),
            'monto_saldo_plataforma': float(deposito.monto_saldo_plataforma),
            'monto':              float(deposito.monto),
            'numero_comprobante': deposito.numero_comprobante or '',
            'diferencia':         float(deposito.diferencia) if deposito.diferencia is not None else None,
            'recaudado_pendiente_momento': float(deposito.recaudado_pendiente_momento) if deposito.recaudado_pendiente_momento is not None else None,
            'saldo_anterior_momento':      float(deposito.saldo_anterior_momento) if deposito.saldo_anterior_momento is not None else None,
            'neto_a_depositar_momento':    float(deposito.neto_a_depositar_momento) if deposito.neto_a_depositar_momento is not None else None,
            'periodo_momento':    periodo_str,
            'recaudaciones_cubiertas_ids': [r.pk for r in seleccionadas],
            'observaciones':      deposito.observaciones or '',
            'realizado_por':      realizado_por_str,
            'nuevo_total':        float(nuevo_total),
        })


class HistorialDepositosView(LoginRequiredMixin, View):
    def get(self, request):
        desde         = request.GET.get('desde',   '').strip()
        hasta         = request.GET.get('hasta',   '').strip()
        entidad       = request.GET.get('entidad', '').strip()

        qs = (
            DepositoBancario.objects
            .select_related('realizado_por')
            .prefetch_related('recaudaciones_cubiertas', 'tickets')
            .all()
        )

        if desde:
            qs = qs.filter(fecha__gte=desde)
        if hasta:
            qs = qs.filter(fecha__lte=hasta)
        if entidad in ENTIDADES_VALIDAS:
            qs = qs.filter(entidad=entidad)

        total_filtrado = qs.aggregate(t=Sum('monto'))['t'] or Decimal('0')

        def _total_ent(ent):
            return (qs.filter(entidad=ent).aggregate(t=Sum('monto'))['t']
                    or Decimal('0'))
        total_pf_filtrado = _total_ent(DepositoBancario.ENTIDAD_PAGOFACIL)
        total_rp_filtrado = _total_ent(DepositoBancario.ENTIDAD_RAPIPAGO)
        total_wu_filtrado = _total_ent(DepositoBancario.ENTIDAD_WESTERN_UNION)

        return render(request, 'cobranzas/historial_depositos.html', {
            'depositos':          _marcar_tickets_cargados(qs[:500]),
            'desde':              desde,
            'hasta':              hasta,
            'entidad':            entidad,
            'total_filtrado':     total_filtrado,
            'total_pf_filtrado':  total_pf_filtrado,
            'total_rp_filtrado':  total_rp_filtrado,
            'total_wu_filtrado':  total_wu_filtrado,
            'ENTIDAD_PF':         DepositoBancario.ENTIDAD_PAGOFACIL,
            'ENTIDAD_RP':         DepositoBancario.ENTIDAD_RAPIPAGO,
            'ENTIDAD_WU':         DepositoBancario.ENTIDAD_WESTERN_UNION,
        })
    

class TicketDepositoAjax(LoginRequiredMixin, View):
    """
    Ver/editar el comprobante asociado a un DepositoBancario. Un depósito
    puede tener hasta 3 tickets (uno por componente: efectivo/banco/
    plataforma) — el parámetro `tipo` identifica cuál.
    """

    CAMPOS_TEXTO = [
        'numero_operacion', 'banco', 'titular_nombre', 'titular_cuit',
        'cuenta_origen', 'destinatario', 'cuenta_destino', 'sucursal',
        'concepto', 'estado', 'observaciones',
    ]

    def _validar_tipo(self, tipo):
        return tipo if tipo in dict(DepositoTicket.TIPOS) else None

    def get(self, request):
        deposito_id = request.GET.get('deposito_id')
        tipo = self._validar_tipo(request.GET.get('tipo', ''))
        if tipo is None:
            return JsonResponse({'error': 'Tipo de ticket inválido.'}, status=400)

        deposito = get_object_or_404(DepositoBancario, pk=deposito_id)
        ticket = DepositoTicket.objects.filter(deposito=deposito, tipo=tipo).first()

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
        tipo = self._validar_tipo(request.POST.get('tipo', ''))
        if tipo is None:
            return JsonResponse({'error': 'Tipo de ticket inválido.'}, status=400)

        deposito = get_object_or_404(DepositoBancario, pk=deposito_id)
        ticket, _ = DepositoTicket.objects.get_or_create(deposito=deposito, tipo=tipo)

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
            'tipo':        tipo,
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


class UsarSaldoFavorAjax(LoginRequiredMixin, View):
    """
    Registra un uso del saldo a favor (ej: carga de SUBE con el crédito de
    la plataforma) que no pasa por un depósito real. Resta del saldo a
    favor vigente vía AjusteSaldoFavor — ver _ultima_diferencia().
    """
    def post(self, request):
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        entidad = data.get('entidad', '').strip()
        if entidad not in ENTIDADES_VALIDAS:
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

        motivo = data.get('motivo', '').strip()
        if not motivo:
            return JsonResponse({'error': 'Indicá para qué se usó el saldo (ej: carga SUBE).'}, status=400)

        observaciones = data.get('observaciones', '').strip()

        with transaction.atomic():
            uso = AjusteSaldoFavor.objects.create(
                entidad=entidad,
                fecha=fecha,
                monto=monto,
                motivo=motivo,
                observaciones=observaciones,
                registrado_por=request.user,
            )

        saldo_anterior = _ultima_diferencia(entidad)
        totales = _totales_por_entidad(entidad)

        try:
            realizado_por_str = request.user.get_full_name() or request.user.username
        except Exception:
            realizado_por_str = str(request.user.pk)

        return JsonResponse({
            'success':            True,
            'uso_id':             uso.pk,
            'fecha':              uso.fecha.strftime('%d/%m/%Y'),
            'monto':              float(uso.monto),
            'motivo':             uso.motivo,
            'observaciones':      uso.observaciones or '',
            'realizado_por':      realizado_por_str,
            'saldo_anterior':     float(saldo_anterior) if saldo_anterior is not None else None,
            'neto_a_depositar':   float(totales['pendiente_mostrar']),
            'a_favor':            float(totales['a_favor']),
        })


class EliminarUsoSaldoFavorAjax(LoginRequiredMixin, View):
    """Elimina un AjusteSaldoFavor. Solo staff/superuser."""
    def post(self, request):
        if not (request.user.is_staff or request.user.is_superuser):
            return JsonResponse({'error': 'Solo administradores pueden eliminar usos de saldo a favor.'}, status=403)

        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        uso_id = data.get('id')
        if not uso_id:
            return JsonResponse({'error': 'No se recibió el ID.'}, status=400)

        uso = get_object_or_404(AjusteSaldoFavor, pk=uso_id)
        entidad = uso.entidad

        with transaction.atomic():
            uso.delete()

        saldo_anterior = _ultima_diferencia(entidad)
        totales = _totales_por_entidad(entidad)

        return JsonResponse({
            'success':          True,
            'entidad':          entidad,
            'saldo_anterior':   float(saldo_anterior) if saldo_anterior is not None else None,
            'neto_a_depositar': float(totales['pendiente_mostrar']),
            'a_favor':          float(totales['a_favor']),
        })