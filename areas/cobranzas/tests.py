import json
from decimal import Decimal as D
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Usuario

from .models import CierreDiario, Cobro, ComisionEntidad, ItemCobro, PagoCobro, Servicio, Turno
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
    """PagoFácil se recauda solo en efectivo; RapiPago todo junto (menos su comisión)."""

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
        self.assertEqual(s['valor_facial'], D('1500'))
        self.assertEqual(s['comision'], D('110.00'))    # 2 boletas × $55 (cargado por la migración)
        self.assertEqual(s['boletas'], D('1390.00'))

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
        self.assertEqual(_sistema_por_canal('rapipago', self.hoy)['valor_facial'], D('700'))


class ComisionRapipagoTests(TestCase):
    """RapiPago descuenta $55 por boleta de lo que se declara (columna "Débito")."""

    def setUp(self):
        self.turno = Turno.objects.create(monto_inicial=D('0'))
        self.srv = _servicio()
        self.hoy = timezone.localdate()

    def test_resumen_real_de_rapipago(self):
        # Los 4 cobros del resumen "Transacciones Online PosPago" del 24/11/2026
        # (Valor facial − $55 = Débito en cada fila; total Débito = facial − 4 × 55).
        faciales = ['295485.48', '84415.24', '22000.00', '12487.00']
        for facial, medio in zip(faciales, ['efectivo', 'debito', 'efectivo', 'transferencia']):
            _cobro(self.turno, [(self.srv, facial, '500', 'rapipago')], [(medio, D(facial) + 500)])
        s = _sistema_por_canal('rapipago', self.hoy)
        self.assertEqual(s['valor_facial'], D('414387.72'))
        self.assertEqual(s['comision_cant'], 4)
        self.assertEqual(s['comision'], D('220.00'))
        self.assertEqual(s['boletas'], D('414167.72'))    # lo que se declara

    def test_cada_cambio_de_comision_rige_desde_su_fecha(self):
        _cobro(self.turno, [(self.srv, '1000', '0', 'rapipago')], [('efectivo', '1000')])
        ComisionEntidad.objects.create(entidad='rapipago', monto_por_boleta=D('70'),
                                       vigente_desde=self.hoy + timezone.timedelta(days=1))
        self.assertEqual(_sistema_por_canal('rapipago', self.hoy)['comision'], D('55.00'))
        ComisionEntidad.objects.create(entidad='rapipago', monto_por_boleta=D('60'), vigente_desde=self.hoy)
        self.assertEqual(_sistema_por_canal('rapipago', self.hoy)['comision'], D('60.00'))

    def test_pagofacil_no_tiene_comision(self):
        _cobro(self.turno, [(self.srv, '1000', '0', 'pagofacil')], [('efectivo', '1000')])
        s = _sistema_por_canal('pagofacil', self.hoy)
        self.assertEqual(s['comision'], D('0'))
        self.assertEqual(s['boletas'], D('1000'))

    def test_solo_staff_cambia_la_comision(self):
        url = reverse('cobranzas:recaudaciones_comision')
        body = json.dumps({'entidad': 'rapipago', 'monto': '60', 'vigente_desde': str(self.hoy)})
        cajero = Usuario.objects.create_user('cajero_comun', 'x@test.local', 'x')
        self.client.force_login(cajero)
        self.assertEqual(self.client.post(url, body, content_type='application/json').status_code, 403)
        admin = Usuario.objects.create_superuser('admin_test', 'a@test.local', 'x')
        self.client.force_login(admin)
        r = self.client.post(url, body, content_type='application/json')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(ComisionEntidad.vigente('rapipago', self.hoy).monto_por_boleta, D('60'))


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
        self.assertEqual(item.monto_redondeo, D('58'))
        self.assertEqual(cobro.total_redondeo(), D('58'))
        self.assertEqual(self.turno.total_efectivo(), D('300'))
        self.assertEqual(self.turno.total_adicionales(), D('158'))
        self.assertEqual(self.turno.total_redondeos(), D('58'))
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
        red = dict(ItemCobro.objects.values_list('servicio__codigo', 'monto_redondeo'))
        self.assertEqual(red, {'CF1': D('20'), 'ACN1': D('0')})

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
        self.assertEqual(cobro.total_redondeo(), D('0'))
        self.assertEqual(cobro.items.get().monto_servicio, D('28246.28'))

    def test_editar_conserva_y_corrige_el_redondeo(self):
        self._confirmar(
            [{'servicio_id': self.srv.pk, 'monto_servicio': 142, 'monto_adicional': 100, 'canal': 'pagofacil'}],
            [{'metodo': 'efectivo', 'monto': 300}], redondeo=58)
        cobro = Cobro.objects.get()
        url = reverse('cobranzas:cobro_editar', args=[cobro.pk])

        def editar(fac, adi, pago, red=None):
            item = {'servicio_id': self.srv.pk, 'monto_servicio': fac, 'monto_adicional': adi,
                    'canal': 'rapipago'}
            if red is not None:
                item['monto_redondeo'] = red
            return self.client.post(url, json.dumps({
                'items': [item], 'pagos': [{'metodo': 'efectivo', 'monto': pago}]}),
                content_type='application/json')

        # Edición sin tocar montos (ej. solo cambia el canal): el redondeo queda.
        self.assertEqual(editar(142, 158, 300, red=58).status_code, 200)
        self.assertEqual(cobro.items.get().monto_redondeo, D('58'))
        # El redondeo nunca puede ser mayor que el adicional de la boleta.
        editar(142, 40, 182, red=58)
        self.assertEqual(cobro.items.get().monto_redondeo, D('40'))
        # Corregir un cobro viejo con el redondeo metido en la factura (196,28 en vez de 142):
        # se baja la factura y se marca la diferencia como redondeo; el total no cambia.
        editar(142, 158, 300, red=58)
        self.assertEqual(cobro.items.get().monto_servicio, D('142'))
        self.assertEqual(cobro.total_general(), D('300'))
        # Si el front no manda el campo (versión vieja en caché), queda en 0 sin romper.
        self.assertEqual(editar(142, 158, 300).status_code, 200)
        self.assertEqual(cobro.items.get().monto_redondeo, D('0'))


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
        self.assertEqual(c.total_redondeo(), D('0'))
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

        item = c.items.get()
        self.assertEqual(item.monto_redondeo, D('58'))
        self.assertEqual(item.monto_adicional, D('158'))   # 100 → 158 (el ejemplo)
        self.assertEqual(item.monto_servicio, D('142'))    # factura intacta
        self.assertEqual(self.turno.total_efectivo(), efectivo_antes)  # caja intacta
        cierre.refresh_from_db()
        self.assertEqual(cierre.total_adicionales, D('158'))
        self.assertEqual(cierre.total_redondeos, D('58'))
        # El excedente grande (1.200 > 1.000) se deja para revisar a mano.
        self.assertEqual(grande.total_redondeo(), D('0'))
        self.assertEqual(grande.items.get().monto_adicional, D('500'))
        self.assertEqual(exacto.total_redondeo(), D('0'))

        # Correrlo de nuevo no suma dos veces.
        self._correr('--aplicar')
        self.assertEqual(c.items.get().monto_adicional, D('158'))
        cierre.refresh_from_db()
        self.assertEqual(cierre.total_adicionales, D('158'))


class CorregirFacturasRedondeadasTests(TestCase):
    """
    El caso real del 24/11/2026: las 5 boletas de PagoFácil se cargaron con el
    redondeo ADENTRO de la factura (18.246,86 → 18.300, 68.818,74 → 68.900).
    El ticket de PagoFácil dice $248.065,60 en efectivo; el sistema, $248.200.
    """

    def setUp(self):
        self.admin = Usuario.objects.create_superuser('admin_bol', 'b@test.local', 'x')
        self.client.force_login(self.admin)
        self.turno = Turno.objects.create(monto_inicial=D('20000'), cajero=self.admin)
        self.srv = _servicio()
        self.hoy = timezone.localdate()
        self.url = reverse('cobranzas:recaudaciones_boletas')
        # (factura cargada, factura real, medio de pago)
        filas = [('18300', '18246.86', 'debito'), ('68900', '68818.74', 'efectivo'),
                 ('18300', '18246.86', 'efectivo'), ('55600', '55600', 'efectivo'),
                 ('105400', '105400', 'efectivo')]
        self.items = []
        for cargada, real, medio in filas:
            c = _cobro(self.turno, [(self.srv, cargada, '1300', 'pagofacil')],
                       [(medio, D(cargada) + 1300)])
            self.items.append((c.items.get(), D(real)))

    def _post(self, correcciones, entidad='pagofacil'):
        return self.client.post(self.url, json.dumps({
            'entidad': entidad, 'fecha': str(self.hoy),
            'correcciones': [{'item_id': it.pk, 'factura_real': str(real)} for it, real in correcciones],
        }), content_type='application/json')

    def test_lista_marca_lo_que_no_se_declara(self):
        r = self.client.get(self.url, {'entidad': 'pagofacil', 'fecha': str(self.hoy)})
        self.assertEqual(r.status_code, 200)
        boletas = r.json()['boletas']
        self.assertEqual(len(boletas), 5)
        self.assertEqual([b['factor'] for b in boletas], [0, 1, 1, 1, 1])   # el de débito no se declara
        self.assertTrue(r.json()['puede_corregir'])

    def test_caso_real_queda_igual_al_ticket_sin_tocar_la_caja(self):
        self.assertEqual(_sistema_por_canal('pagofacil', self.hoy)['boletas'], D('248200'))
        efectivo_esperado = self.turno.efectivo_esperado()
        totales = [it.cobro.total_general() for it, _ in self.items]

        r = self._post([(it, real) for it, real in self.items if it.monto_servicio != real])
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()['total_redondeo'], 187.54)

        s = _sistema_por_canal('pagofacil', self.hoy)
        self.assertEqual(s['boletas'], D('248065.60'))          # = ticket de PagoFácil
        self.assertEqual(s['redondeos'], D('187.54'))           # incluye el del cobro con débito
        self.assertEqual(self.turno.efectivo_esperado(), efectivo_esperado)   # caja intacta
        for (it, real), total in zip(self.items, totales):
            it.refresh_from_db()
            self.assertEqual(it.monto_servicio, real)
            self.assertEqual(it.cobro.total_general(), total)   # el cobro suma lo mismo
        it = self.items[1][0]
        self.assertEqual((it.monto_adicional, it.monto_redondeo), (D('1381.26'), D('81.26')))
        self.assertIn('68.900,00 → $68.818,74', it.cobro.observaciones)

    def test_actualiza_el_cierre_diario_guardado(self):
        cierre = CierreDiario.objects.create(fecha_desde=self.hoy, fecha_hasta=self.hoy,
                                             total_adicionales=D('6500'), total_general=D('273000'))
        self.turno.cierre_diario = cierre
        self.turno.save()
        self.assertEqual(self._post([self.items[1]]).status_code, 200)
        cierre.refresh_from_db()
        self.assertEqual((cierre.total_adicionales, cierre.total_redondeos, cierre.total_general),
                         (D('6581.26'), D('81.26'), D('273000')))

    def test_rechaza_lo_que_no_es_un_redondeo_sin_cambiar_nada(self):
        it, _ = self.items[1]
        casos = [
            [(it, D('69000'))],                      # mayor que la factura cargada
            [(it, D('6890'))],                       # error de tipeo: diferencia enorme
            [(self.items[2][0], D('18246.86')), (it, D('0'))],   # una mala frena todas
        ]
        for correcciones in casos:
            self.assertEqual(self._post(correcciones).status_code, 400)
        for item, _ in self.items:
            self.assertEqual(ItemCobro.objects.get(pk=item.pk).monto_redondeo, D('0'))
        # Boleta de otro canal (pedida como RapiPago) tampoco.
        self.assertEqual(self._post([(it, D('68818.74'))], entidad='rapipago').status_code, 400)

    def test_solo_quien_puede_editar_cobros(self):
        cajero = Usuario.objects.create_user('cajero_bol', 'cb@test.local', 'x')
        self.client.force_login(cajero)
        self.assertEqual(self._post([self.items[1]]).status_code, 403)
        r = self.client.get(self.url, {'entidad': 'pagofacil', 'fecha': str(self.hoy)})
        self.assertFalse(r.json()['puede_corregir'])


class DiagnosticoCajaTests(TestCase):
    def test_puente_del_total_general_al_efectivo_esperado(self):
        turno = Turno.objects.create(monto_inicial=D('20000'))
        srv = _servicio()
        ext = _servicio('EX1', familia='EX')
        _cobro(turno, [(srv, '68900', '1300', 'pagofacil')], [('efectivo', '70200')])
        _cobro(turno, [(srv, '18300', '1300', 'pagofacil')], [('debito', '19600')])
        _cobro(turno, [(srv, '1000', '100', 'otro')], [('efectivo', '1100')])
        _cobro(turno, [(ext, '4000', '400', 'rapipago')], [('transferencia', '4400')])
        out = StringIO()
        call_command('diagnostico_caja', str(timezone.localdate()), '--contado', '86.400', stdout=out)
        salida = out.getvalue()
        # Historial PF+RP: 70.200 + 19.600 + 4.400 = 94.200 (no es el efectivo del cajón)
        self.assertIn('TOTAL GENERAL:       $94.200,00', salida)
        # 20.000 fondo + 70.200 + 1.100 (canal Otro) − 4.000 entregados en la extracción
        esperado = turno.efectivo_esperado()
        self.assertEqual(esperado, D('87300'))
        self.assertIn('= EFECTIVO ESPERADO                                   $87.300,00', salida)
        self.assertIn('-$900,00   (FALTA)', salida)
        self.assertIn('Facturas "redondas" (múltiplo de $50, sin centavos): 2', salida)   # la EX no cuenta


class RedondeoDesdeElTicketTests(TestCase):
    """
    El redondeo que quedó cargado DENTRO de las facturas se deduce solo del
    ticket de la recaudación, sin corregir los cobros uno por uno.
    Caso real PagoFácil 24/11/2026: sistema $248.200 en efectivo, ticket $248.065,60.
    """

    def setUp(self):
        self.admin = Usuario.objects.create_superuser('admin_red', 'r@test.local', 'x')
        self.client.force_login(self.admin)
        self.turno = Turno.objects.create(monto_inicial=D('0'), cajero=self.admin)
        self.srv = _servicio()
        self.hoy = timezone.localdate()
        filas = [('18300', '1000', 'debito'), ('68900', '1500', 'efectivo'),
                 ('18300', '1000', 'efectivo'), ('55600', '1000', 'efectivo'),
                 ('105400', '2000', 'efectivo')]
        self.cobros = [_cobro(self.turno, [(self.srv, f, a, 'pagofacil')], [(m, D(f) + D(a))])
                       for f, a, m in filas]

    def _registrar(self, monto):
        return self.client.post(reverse('cobranzas:recaudaciones_registrar'), json.dumps({
            'entidad': 'pagofacil', 'fecha': str(self.hoy), 'monto': monto,
        }), content_type='application/json')

    def _rec(self):
        from .models import RecaudacionDiaria
        return RecaudacionDiaria.objects.get(entidad='pagofacil', fecha=self.hoy)

    def test_la_diferencia_a_favor_es_redondeo(self):
        r = self._registrar('248065.60')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()['redondeo'], 134.40)
        self.assertEqual(self._rec().redondeo, D('134.40'))
        from .views_ganancias import _totales
        t = _totales()
        self.assertEqual(t['redondeos'], D('134.40'))
        self.assertEqual(t['ganado'], D('6500') + D('134.40'))
        self.assertEqual(t['adicionales'], D('6500'))

    def test_lo_que_no_parece_redondeo_no_se_toma(self):
        # El ticket tiene MÁS que el sistema: falta algo, no es redondeo.
        self._registrar('248300')
        self.assertEqual(self._rec().redondeo, D('0'))
        # El sistema tiene $8.200 más: más de $1.000 por boleta redonda (4) → revisar.
        self._registrar('240000')
        self.assertEqual(self._rec().redondeo, D('0'))

    def test_corregir_boletas_despues_no_lo_cuenta_dos_veces(self):
        self._registrar('248065.60')
        items = [c.items.get() for c in self.cobros]
        r = self.client.post(reverse('cobranzas:recaudaciones_boletas'), json.dumps({
            'entidad': 'pagofacil', 'fecha': str(self.hoy),
            'correcciones': [{'item_id': items[1].pk, 'factura_real': '68818.74'},
                             {'item_id': items[2].pk, 'factura_real': '18246.86'}],
        }), content_type='application/json')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(self._rec().redondeo, D('0'))      # ya está en cada boleta
        from .views_ganancias import _totales
        self.assertEqual(_totales()['redondeos'], D('134.40'))

    def test_editar_un_cobro_recalcula(self):
        self._registrar('248065.60')
        c = self.cobros[1]
        r = self.client.post(reverse('cobranzas:cobro_editar', args=[c.pk]), json.dumps({
            'items': [{'servicio_id': self.srv.pk, 'monto_servicio': 68818.74,
                       'monto_adicional': 1581.26, 'monto_redondeo': 81.26, 'canal': 'pagofacil'}],
            'pagos': [{'metodo': 'efectivo', 'monto': 70400}],
        }), content_type='application/json')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(self._rec().redondeo, D('53.14'))   # queda solo el de la otra boleta

    def test_historial_lo_suma_a_las_tarjetas(self):
        self._registrar('248065.60')
        url = reverse('cobranzas:historial_cobros')
        r = self.client.get(url, {'desde': str(self.hoy), 'hasta': str(self.hoy), 'canales': 'pagofacil'})
        self.assertEqual(r.context['redondeo_recaudaciones'], D('134.40'))
        r = self.client.get(url, {'desde': str(self.hoy), 'canales': 'rapipago'})
        self.assertEqual(r.context['redondeo_recaudaciones'], D('0'))
        r = self.client.get(url, {'desde': str(self.hoy), 'metodos': 'efectivo'})
        self.assertEqual(r.context['redondeo_recaudaciones'], D('0'))
