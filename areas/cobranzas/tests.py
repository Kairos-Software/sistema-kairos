import json
from decimal import Decimal as D
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Usuario

from .models import CierreDiario, Cobro, ItemCobro, PagoCobro, Servicio, Turno
from .views_recaudaciones import _sistema_por_canal


def _servicio(codigo='CF1', familia='CF', tipo=Servicio.TIPO_RANGO):
    return Servicio.objects.create(codigo=codigo, descripcion=codigo, monto=D('100'),
                                   familia=familia, tipo_precio=tipo,
                                   rango_desde=D('0'), rango_hasta=D('999999'))


def _cobro(turno, items, pagos):
    """items: [(servicio, factura, adicional, canal)] ; pagos: [(metodo, monto)]"""
    c = Cobro.objects.create(turno=turno, estado=Cobro.ESTADO_CERRADO, fecha_cierre=timezone.now())
    for srv, fac, adi, canal in items:
        ItemCobro.objects.create(cobro=c, servicio=srv, monto_servicio=D(fac),
                                 monto_adicional=D(adi), canal=canal)
    for met, monto in pagos:
        PagoCobro.objects.create(cobro=c, metodo=met, monto=D(monto))
    return c


class RecaudacionSegunEntidadTests(TestCase):
    """PagoFácil se recauda solo en efectivo; RapiPago todo junto."""

    def setUp(self):
        self.turno = Turno.objects.create(monto_inicial=D('0'))
        self.srv = _servicio()
        self.hoy = timezone.localdate()

    def test_pagofacil_cuenta_solo_lo_cobrado_en_efectivo(self):
        # El caso real: 248.200 en efectivo + 18.300 cobrados sin efectivo.
        _cobro(self.turno, [(self.srv, '248200', '1000', 'pagofacil')], [('efectivo', '249200')])
        _cobro(self.turno, [(self.srv, '18300', '300', 'pagofacil')], [('debito', '18600')])
        s = _sistema_por_canal('pagofacil', self.hoy)
        self.assertTrue(s['solo_efectivo'])
        self.assertEqual(s['boletas'], D('248200'))
        self.assertEqual(s['boletas_otros'], D('18300'))
        self.assertEqual(s['boletas_todos'], D('266500'))
        self.assertEqual(s['cant'], 2)
        self.assertEqual(s['cant_otros'], 1)

    def test_rapipago_cuenta_todos_los_medios(self):
        _cobro(self.turno, [(self.srv, '1000', '100', 'rapipago')], [('efectivo', '1100')])
        _cobro(self.turno, [(self.srv, '500', '50', 'rapipago')], [('transferencia', '550')])
        s = _sistema_por_canal('rapipago', self.hoy)
        self.assertFalse(s['solo_efectivo'])
        self.assertEqual(s['boletas'], D('1500'))

    def test_pago_mixto_se_estima_en_proporcion(self):
        # 1000 de factura, se pagó 600 efectivo + 600 débito → mitad en efectivo.
        _cobro(self.turno, [(self.srv, '1000', '200', 'pagofacil')],
               [('efectivo', '600'), ('debito', '600')])
        s = _sistema_por_canal('pagofacil', self.hoy)
        self.assertEqual(s['cant_mixto'], 1)
        self.assertEqual(s['boletas_mixto'], D('1000'))
        self.assertEqual(s['mixto_efectivo_estimado'], D('500.00'))
        self.assertEqual(s['boletas'], D('500.00'))

    def test_solo_cuenta_el_canal_pedido(self):
        _cobro(self.turno, [(self.srv, '1000', '0', 'pagofacil'), (self.srv, '700', '0', 'rapipago')],
               [('efectivo', '1700')])
        self.assertEqual(_sistema_por_canal('pagofacil', self.hoy)['boletas'], D('1000'))
        self.assertEqual(_sistema_por_canal('rapipago', self.hoy)['boletas'], D('700'))


class RedondeoAlConfirmarTests(TestCase):
    def setUp(self):
        self.user = Usuario.objects.create_superuser('cajero_test', 'c@test.local', 'x')
        self.client.force_login(self.user)
        self.turno = Turno.objects.create(monto_inicial=D('0'), cajero=self.user)
        self.srv = _servicio()

    def _confirmar(self, items, pagos, redondeo=None):
        body = {'items': items, 'pagos': pagos}
        if redondeo is not None:
            body['redondeo'] = redondeo
        return self.client.post(reverse('cobranzas:cobro_confirmar'), json.dumps(body),
                                content_type='application/json')

    def test_ejemplo_142_mas_100_cobrado_300(self):
        r = self._confirmar(
            [{'servicio_id': self.srv.pk, 'monto_servicio': 142, 'monto_adicional': 100, 'canal': 'pagofacil'}],
            [{'metodo': 'efectivo', 'monto': 300}], redondeo=58)
        self.assertEqual(r.status_code, 200, r.content)
        cobro = Cobro.objects.get()
        item = cobro.items.get()
        self.assertEqual(item.monto_servicio, D('142'))     # la factura no se toca
        self.assertEqual(item.monto_adicional, D('158'))    # 100 + 58 de redondeo
        self.assertEqual(cobro.redondeo, D('58'))
        self.assertEqual(self.turno.total_efectivo(), D('300'))
        self.assertEqual(self.turno.total_adicionales(), D('158'))
        self.assertEqual(r.json()['redondeo'], 58.0)

    def test_el_redondeo_va_a_un_item_con_cantidad_1(self):
        fijo = _servicio('ACN1', 'ACN', Servicio.TIPO_FIJO)
        r = self._confirmar(
            [{'servicio_id': self.srv.pk, 'monto_servicio': 100, 'monto_adicional': 10, 'canal': 'pagofacil'},
             {'servicio_id': fijo.pk, 'monto_servicio': 50, 'monto_adicional': 20, 'cantidad': 2, 'canal': 'otro'}],
            [{'metodo': 'efectivo', 'monto': 200}], redondeo=20)
        self.assertEqual(r.status_code, 200, r.content)
        adic = dict(ItemCobro.objects.values_list('servicio__codigo', 'monto_adicional'))
        self.assertEqual(adic, {'CF1': D('30'), 'ACN1': D('20')})

    def test_los_pagos_tienen_que_cubrir_el_redondeo(self):
        r = self._confirmar(
            [{'servicio_id': self.srv.pk, 'monto_servicio': 142, 'monto_adicional': 100, 'canal': 'pagofacil'}],
            [{'metodo': 'efectivo', 'monto': 242}], redondeo=58)
        self.assertEqual(r.status_code, 400)
        self.assertFalse(Cobro.objects.exists())

    def test_redondeo_negativo_se_rechaza(self):
        r = self._confirmar(
            [{'servicio_id': self.srv.pk, 'monto_servicio': 142, 'monto_adicional': 100, 'canal': 'pagofacil'}],
            [{'metodo': 'efectivo', 'monto': 242}], redondeo=-2)
        self.assertEqual(r.status_code, 400)

    def test_sin_redondeo_funciona_como_antes(self):
        r = self._confirmar(
            [{'servicio_id': self.srv.pk, 'monto_servicio': '28246.28', 'monto_adicional': 500, 'canal': 'pagofacil'}],
            [{'metodo': 'efectivo', 'monto': '28746.28'}])
        self.assertEqual(r.status_code, 200, r.content)
        cobro = Cobro.objects.get()
        self.assertEqual(cobro.redondeo, D('0'))
        self.assertEqual(cobro.items.get().monto_servicio, D('28246.28'))

    def test_editar_conserva_el_redondeo_y_lo_limita_al_adicional(self):
        self._confirmar(
            [{'servicio_id': self.srv.pk, 'monto_servicio': 142, 'monto_adicional': 100, 'canal': 'pagofacil'}],
            [{'metodo': 'efectivo', 'monto': 300}], redondeo=58)
        cobro = Cobro.objects.get()
        url = reverse('cobranzas:cobro_editar', args=[cobro.pk])
        # Edición sin tocar montos (ej. solo cambia el canal): el redondeo queda.
        self.client.post(url, json.dumps({
            'items': [{'servicio_id': self.srv.pk, 'monto_servicio': 142, 'monto_adicional': 158, 'canal': 'rapipago'}],
            'pagos': [{'metodo': 'efectivo', 'monto': 300}]}), content_type='application/json')
        cobro.refresh_from_db()
        self.assertEqual(cobro.redondeo, D('58'))
        # Se baja el adicional a 40: el redondeo no puede quedar mayor que eso.
        self.client.post(url, json.dumps({
            'items': [{'servicio_id': self.srv.pk, 'monto_servicio': 142, 'monto_adicional': 40, 'canal': 'rapipago'}],
            'pagos': [{'metodo': 'efectivo', 'monto': 182}]}), content_type='application/json')
        cobro.refresh_from_db()
        self.assertEqual(cobro.redondeo, D('40'))


class ConvertirExcedentesTests(TestCase):
    def setUp(self):
        self.turno = Turno.objects.create(monto_inicial=D('0'))
        self.srv = _servicio()

    def _correr(self, *args):
        out = StringIO()
        call_command('convertir_excedentes_en_redondeo', *args, stdout=out)
        return out.getvalue()

    def test_sin_aplicar_no_cambia_nada(self):
        c = _cobro(self.turno, [(self.srv, '142', '100', 'pagofacil')], [('efectivo', '300')])
        salida = self._correr()
        self.assertIn('Cobros a convertir: 1', salida)
        c.refresh_from_db()
        self.assertEqual(c.redondeo, D('0'))
        self.assertEqual(c.items.get().monto_adicional, D('100'))

    def test_aplicar_convierte_el_excedente_sin_tocar_caja_ni_facturas(self):
        cierre = CierreDiario.objects.create(fecha_desde=timezone.localdate(), fecha_hasta=timezone.localdate(),
                                             total_adicionales=D('100'))
        self.turno.cierre_diario = cierre
        self.turno.save()
        c = _cobro(self.turno, [(self.srv, '142', '100', 'pagofacil')], [('efectivo', '300')])
        grande = _cobro(self.turno, [(self.srv, '28300', '500', 'pagofacil')], [('efectivo', '30000')])
        exacto = _cobro(self.turno, [(self.srv, '1000', '100', 'pagofacil')], [('efectivo', '1100')])
        efectivo_antes = self.turno.total_efectivo()

        self._correr('--aplicar')

        c.refresh_from_db()
        item = c.items.get()
        self.assertEqual(c.redondeo, D('58'))
        self.assertEqual(item.monto_adicional, D('158'))   # 100 → 158 (el ejemplo)
        self.assertEqual(item.monto_servicio, D('142'))    # factura intacta
        self.assertEqual(self.turno.total_efectivo(), efectivo_antes)  # caja intacta
        cierre.refresh_from_db()
        self.assertEqual(cierre.total_adicionales, D('158'))
        # El excedente grande (1.200 > 1.000) se deja para revisar a mano.
        grande.refresh_from_db()
        self.assertEqual(grande.redondeo, D('0'))
        self.assertEqual(grande.items.get().monto_adicional, D('500'))
        exacto.refresh_from_db()
        self.assertEqual(exacto.redondeo, D('0'))

        # Correrlo de nuevo no suma dos veces.
        self._correr('--aplicar')
        c.refresh_from_db()
        self.assertEqual(c.items.get().monto_adicional, D('158'))
        cierre.refresh_from_db()
        self.assertEqual(cierre.total_adicionales, D('158'))
