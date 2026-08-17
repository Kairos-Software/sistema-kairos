import re
from decimal import Decimal

from django.db import models
from django.utils import timezone
from core.models import Usuario


# ─────────────────────────────────────────────────────────────
# SINCRONIZACIÓN descripcion <-> rango_desde/rango_hasta
#
# La descripcion de los servicios "por rango" suele traer el rango
# escrito en prosa (ej: "Extracciones/Retiro de Efectivo Desde
# $600.001/Hasta $700.000"), heredado del Excel de origen. Si alguien
# edita rango_desde/rango_hasta a mano (formulario o CSV) sin tocar
# ese texto, quedan desincronizados y el usuario ve un número en la
# descripción que ya no es el que usa el sistema para cobrar — muy
# confuso. Server.save() reescribe automáticamente los números
# encontrados en la descripción para que siempre coincidan.
# ─────────────────────────────────────────────────────────────

_PATRON_DESDE_HASTA_ABIERTO = re.compile(
    r'desde\s*\$?\s*([\d.,]+)\s*/\s*en\s*adelante', re.IGNORECASE)
_PATRON_DESDE_HASTA = re.compile(
    r'desde\s*\$?\s*([\d.,]+)\s*/\s*hasta\s*\$?\s*([\d.,]+)', re.IGNORECASE)
_PATRON_DE_A_ABIERTO = re.compile(
    r'\bde\s*\$?\s*([\d.,]+)\s*en\s*adelante', re.IGNORECASE)
_PATRON_DE_A = re.compile(
    r'\bde\s*\$?\s*([\d.,]+)\s*a\s*\$?\s*([\d.,]+)', re.IGNORECASE)


def _formato_monto_ar(valor: Decimal) -> str:
    """2400 -> '2.400' ; 600001 -> '600.001' (formato de miles con punto, sin decimales)."""
    return f"{int(valor):,}".replace(',', '.')


def sincronizar_rango_en_descripcion(descripcion: str, rango_desde, rango_hasta) -> str:
    """
    Reescribe los números de rango dentro de descripcion para que
    coincidan con rango_desde/rango_hasta, preservando el resto del
    texto (prefijo, "$", "/", etc). Si no reconoce ningún patrón de
    rango en el texto, lo deja intacto (no fuerza nada).
    """
    if descripcion is None or rango_desde is None or rango_hasta is None:
        return descripcion

    desde_fmt = _formato_monto_ar(rango_desde)
    hasta_fmt = _formato_monto_ar(rango_hasta)

    for patron, con_hasta in (
        (_PATRON_DESDE_HASTA_ABIERTO, False),
        (_PATRON_DESDE_HASTA,         True),
        (_PATRON_DE_A_ABIERTO,        False),
        (_PATRON_DE_A,                True),
    ):
        m = patron.search(descripcion)
        if not m:
            continue
        if con_hasta:
            return (
                descripcion[:m.start(1)] + desde_fmt +
                descripcion[m.end(1):m.start(2)] + hasta_fmt +
                descripcion[m.end(2):]
            )
        return descripcion[:m.start(1)] + desde_fmt + descripcion[m.end(1):]

    return descripcion


# ─────────────────────────────────────────────────────────────
# SERVICIO
# ─────────────────────────────────────────────────────────────

class Servicio(models.Model):
    TIPO_FIJO  = 'fijo'
    TIPO_RANGO = 'rango'
    TIPOS_PRECIO = [
        (TIPO_FIJO,  'Fijo'),
        (TIPO_RANGO, 'Por rango'),
    ]

    codigo      = models.CharField(max_length=20, unique=True)
    descripcion = models.CharField(max_length=300)
    monto       = models.DecimalField(max_digits=12, decimal_places=2,
                                       help_text="Precio fijo, o adicional a cobrar cuando tipo_precio='rango'")
    activo      = models.BooleanField(default=True)
    proveedor   = models.CharField(max_length=100, blank=True)

    familia     = models.CharField(max_length=20, blank=True, db_index=True,
                                    help_text="Agrupa los tramos de un mismo servicio escalonado (ej: CF, EX, TNBV)")
    tipo_precio = models.CharField(max_length=10, choices=TIPOS_PRECIO, default=TIPO_FIJO)
    rango_desde = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True,
                                       help_text="Solo si tipo_precio='rango': monto mínimo de boleta cubierto por este tramo")
    rango_hasta = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True,
                                       help_text="Solo si tipo_precio='rango': monto máximo de boleta cubierto por este tramo")

    creado_por       = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True, blank=True,
                                         related_name='servicios_creados')
    fecha_creacion   = models.DateTimeField(auto_now_add=True)
    modificado_por   = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True, blank=True,
                                         related_name='servicios_modificados')
    fecha_modificacion = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['codigo']

    def __str__(self):
        return f"{self.codigo} - {self.descripcion[:40]}"

    def save(self, *args, **kwargs):
        if self.tipo_precio == self.TIPO_RANGO:
            self.descripcion = sincronizar_rango_en_descripcion(
                self.descripcion, self.rango_desde, self.rango_hasta
            )
        super().save(*args, **kwargs)


# ─────────────────────────────────────────────────────────────
# PREFIJO SERVICIO
# Prefijos ("familia") reservados desde la UI de Servicios antes de
# tener ningún Servicio cargado todavía con ese código (ej: se crea
# el prefijo "TR" para empezar a cargar trámites). Persistido en DB
# para sobrevivir reinicios y ser consistente entre todos los
# workers en producción (antes era una lista en memoria de proceso).
# ─────────────────────────────────────────────────────────────

class PrefijoServicio(models.Model):
    codigo = models.CharField(max_length=10, unique=True)

    class Meta:
        ordering = ['codigo']
        verbose_name        = 'Prefijo de servicio'
        verbose_name_plural = 'Prefijos de servicio'

    def __str__(self):
        return self.codigo


# ─────────────────────────────────────────────────────────────
# TURNO
# Representa una sesión de caja abierta por un cajero.
# Puede haber varios turnos por día.
# Un cobro siempre pertenece a un turno abierto.
# ─────────────────────────────────────────────────────────────

class Turno(models.Model):
    ESTADO_ABIERTO = 'abierto'
    ESTADO_CERRADO = 'cerrado'
    ESTADOS = [
        (ESTADO_ABIERTO, 'Abierto'),
        (ESTADO_CERRADO, 'Cerrado'),
    ]

    TIPO_DIF_SOBRANTE    = 'sobrante'
    TIPO_DIF_FALTANTE    = 'faltante'
    TIPO_DIF_SIN_DIF     = 'sin_diferencia'
    TIPOS_DIF = [
        (TIPO_DIF_SOBRANTE, 'Sobrante'),
        (TIPO_DIF_FALTANTE, 'Faltante'),
        (TIPO_DIF_SIN_DIF,  'Sin diferencia'),
    ]

    numero          = models.PositiveIntegerField(unique=True, editable=False)
    estado          = models.CharField(max_length=10, choices=ESTADOS, default=ESTADO_ABIERTO)
    monto_inicial   = models.DecimalField(max_digits=12, decimal_places=2, default=0,
                                          help_text="Efectivo con que abre la caja (fondo para vueltos)")
    fecha_apertura  = models.DateTimeField(auto_now_add=True)
    fecha_cierre    = models.DateTimeField(null=True, blank=True)
    cajero          = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True,
                                        related_name='turnos')

    # Campos que se completan al cerrar el turno
    efectivo_declarado  = models.DecimalField(max_digits=12, decimal_places=2,
                                               null=True, blank=True,
                                               help_text="Efectivo físico contado al cierre")
    total_efectivo_sistema = models.DecimalField(max_digits=12, decimal_places=2,
                                                  null=True, blank=True,
                                                  help_text="Efectivo cobrado según el sistema")
    diferencia      = models.DecimalField(max_digits=12, decimal_places=2,
                                          null=True, blank=True,
                                          help_text="efectivo_declarado − efectivo_esperado")
    tipo_diferencia = models.CharField(max_length=20, choices=TIPOS_DIF,
                                       null=True, blank=True)

    # FK al cierre diario que incluye este turno (null = aún no cerrado)
    cierre_diario   = models.ForeignKey('CierreDiario', on_delete=models.SET_NULL,
                                         null=True, blank=True,
                                         related_name='turnos')

    class Meta:
        ordering = ['-fecha_apertura']

    def __str__(self):
        return f"Turno #{self.numero} — {self.get_estado_display()} — {self.cajero}"

    def save(self, *args, **kwargs):
        if not self.pk:
            ultimo = Turno.objects.order_by('-numero').values_list('numero', flat=True).first()
            self.numero = (ultimo or 0) + 1
        super().save(*args, **kwargs)

    # ── helpers ──────────────────────────────────────────────

    def total_por_metodo(self, metodo):
        from django.db.models import Sum
        return (
            PagoCobro.objects
            .filter(cobro__turno=self, cobro__estado=Cobro.ESTADO_CERRADO, metodo=metodo)
            .aggregate(t=Sum('monto'))['t'] or 0
        )

    def total_efectivo(self):
        return self.total_por_metodo(PagoCobro.METODO_EFECTIVO)

    def total_transferencia(self):
        return self.total_por_metodo(PagoCobro.METODO_TRANSFERENCIA)

    def total_debito(self):
        return self.total_por_metodo(PagoCobro.METODO_DEBITO)

    def total_credito(self):
        return self.total_por_metodo(PagoCobro.METODO_CREDITO)

    def total_qr(self):
        return self.total_por_metodo(PagoCobro.METODO_QR)

    def total_retiros(self):
        from django.db.models import Sum
        return self.retiros.filter(activo=True).aggregate(t=Sum('monto'))['t'] or 0

    def total_general(self):
        """Suma de todos los cobros sin importar el método."""
        from django.db.models import Sum
        return (
            PagoCobro.objects
            .filter(cobro__turno=self, cobro__estado=Cobro.ESTADO_CERRADO)
            .aggregate(t=Sum('monto'))['t'] or 0
        )

    def efectivo_esperado(self):
        """Cuánto efectivo debería haber en caja al cierre."""
        return self.monto_inicial + self.total_efectivo() - self.total_retiros()

    def total_adicionales(self):
        from django.db.models import Sum
        return (
            ItemCobro.objects
            .filter(cobro__turno=self, cobro__estado=Cobro.ESTADO_CERRADO)
            .aggregate(t=Sum('monto_adicional'))['t'] or 0
        )


# ─────────────────────────────────────────────────────────────
# RETIRO DE CAJA
# Salidas de efectivo durante un turno (gastos, depósitos, etc.)
# Reducen el efectivo esperado al cierre.
# ─────────────────────────────────────────────────────────────

class RetiroCaja(models.Model):
    turno       = models.ForeignKey(Turno, on_delete=models.CASCADE, related_name='retiros')
    motivo      = models.CharField(max_length=200)
    monto       = models.DecimalField(max_digits=12, decimal_places=2)
    fecha       = models.DateTimeField(auto_now_add=True)
    registrado_por = models.ForeignKey(Usuario, on_delete=models.SET_NULL,
                                        null=True, related_name='retiros_registrados')
    activo      = models.BooleanField(default=True,
                                      help_text="False = anulado, no cuenta en el balance")

    class Meta:
        ordering = ['-fecha']

    def __str__(self):
        return f"Retiro ${self.monto} — {self.motivo[:40]} (Turno #{self.turno.numero})"


# ─────────────────────────────────────────────────────────────
# COBRO
# ─────────────────────────────────────────────────────────────

class Cobro(models.Model):
    ESTADO_ABIERTO = 'abierto'
    ESTADO_CERRADO = 'cerrado'
    ESTADO_ANULADO = 'anulado'
    ESTADOS = [
        (ESTADO_ABIERTO, 'Abierto'),
        (ESTADO_CERRADO, 'Cerrado'),
        (ESTADO_ANULADO, 'Anulado'),
    ]

    turno           = models.ForeignKey(Turno, on_delete=models.PROTECT,
                                         null=True, blank=True, related_name='cobros',
                                         help_text="Turno en que se realizó el cobro")
    estado          = models.CharField(max_length=10, choices=ESTADOS, default=ESTADO_ABIERTO)
    fecha_creacion  = models.DateTimeField(auto_now_add=True)
    fecha_cierre    = models.DateTimeField(null=True, blank=True)
    creado_por      = models.ForeignKey(Usuario, on_delete=models.SET_NULL,
                                         null=True, blank=True, related_name='cobros_creados')
    observaciones   = models.TextField(blank=True)

    class Meta:
        ordering = ['-fecha_creacion']

    def __str__(self):
        return f"Cobro #{self.pk} — {self.get_estado_display()} — {self.fecha_creacion:%d/%m/%Y %H:%M}"

    def total_adicionales(self):
        from django.db.models import Sum
        return self.items.aggregate(t=Sum('monto_adicional'))['t'] or 0

    def total_boletas(self):
        from django.db.models import Sum
        return self.items.aggregate(t=Sum('monto_servicio'))['t'] or 0

    def total_general(self):
        return self.total_boletas() + self.total_adicionales()

    def total_pagado(self):
        from django.db.models import Sum
        return self.pagos.aggregate(t=Sum('monto'))['t'] or 0


# ─────────────────────────────────────────────────────────────
# ITEM COBRO
# ─────────────────────────────────────────────────────────────

class ItemCobro(models.Model):
    CANAL_PAGOFACIL = 'pagofacil'
    CANAL_RAPIPAGO  = 'rapipago'
    CANAL_OTRO      = 'otro'
    CANALES = [
        (CANAL_PAGOFACIL, 'Pago Fácil'),
        (CANAL_RAPIPAGO,  'Rapipago'),
        (CANAL_OTRO,      'Otro'),
    ]

    cobro           = models.ForeignKey(Cobro, on_delete=models.CASCADE, related_name='items')
    servicio        = models.ForeignKey(Servicio, on_delete=models.PROTECT, related_name='cobros')
    monto_servicio  = models.DecimalField(max_digits=12, decimal_places=2)
    monto_adicional = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    canal           = models.CharField(max_length=20, choices=CANALES, default=CANAL_PAGOFACIL)
    orden           = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['orden', 'pk']

    def __str__(self):
        return f"{self.servicio.codigo} — ${self.monto_servicio} + ${self.monto_adicional}"

    def subtotal(self):
        return self.monto_servicio + self.monto_adicional


# ─────────────────────────────────────────────────────────────
# PAGO COBRO
# ─────────────────────────────────────────────────────────────

class PagoCobro(models.Model):
    METODO_EFECTIVO      = 'efectivo'
    METODO_TRANSFERENCIA = 'transferencia'
    METODO_DEBITO        = 'debito'
    METODO_CREDITO       = 'credito'
    METODO_QR            = 'qr'
    METODOS = [
        (METODO_EFECTIVO,      'Efectivo'),
        (METODO_TRANSFERENCIA, 'Transferencia'),
        (METODO_DEBITO,        'Débito'),
        (METODO_CREDITO,       'Crédito'),
        (METODO_QR,            'QR'),
    ]

    cobro   = models.ForeignKey(Cobro, on_delete=models.CASCADE, related_name='pagos')
    metodo  = models.CharField(max_length=20, choices=METODOS)
    monto   = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        ordering = ['pk']

    def __str__(self):
        return f"{self.get_metodo_display()} — ${self.monto}"


# ─────────────────────────────────────────────────────────────
# CIERRE DIARIO
# Agrupa uno o más turnos cerrados y hace el balance final.
# Los turnos incluidos quedan marcados con FK a este cierre
# para que no se cuenten dos veces.
# ─────────────────────────────────────────────────────────────

class CierreDiario(models.Model):
    fecha           = models.DateTimeField(default=timezone.now)
    fecha_desde     = models.DateField(help_text="Primer día del rango de turnos incluidos")
    fecha_hasta     = models.DateField(help_text="Último día del rango de turnos incluidos")
    realizado_por   = models.ForeignKey(Usuario, on_delete=models.SET_NULL,
                                         null=True, related_name='cierres_diarios')

    # Totales del sistema (calculados de los cobros)
    cant_turnos         = models.PositiveSmallIntegerField(default=0)
    total_efectivo      = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_transferencia = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_debito        = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_credito       = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_qr            = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_retiros       = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_general       = models.DecimalField(max_digits=12, decimal_places=2, default=0,
                                               help_text="Suma de todos los métodos de pago")
    total_adicionales   = models.DecimalField(max_digits=12, decimal_places=2, default=0,
                                               help_text="Nuestra ganancia del día")

    # Total físico declarado al cierre
    efectivo_fisico     = models.DecimalField(max_digits=12, decimal_places=2, default=0,
                                               help_text="Efectivo contado físicamente al cierre")
    diferencia_caja     = models.DecimalField(max_digits=12, decimal_places=2, default=0,
                                               help_text="efectivo_fisico − efectivo esperado")

    class Meta:
        ordering = ['-fecha']

    def __str__(self):
        return f"Cierre #{self.pk} — {self.fecha:%d/%m/%Y %H:%M} — {self.cant_turnos} turno(s)"


# ─────────────────────────────────────────────────────────────
# DEPÓSITO BANCARIO
#
# Registra cada depósito bancario realizado, separado por
# entidad (PagoFácil / RapiPago).
#
# El acumulado por entidad se calcula en tiempo real:
#   SUM(CierreDiario.total_general) no aplica aquí —
#   el monto a depositar lo ingresa el usuario manualmente.
#   El historial de depósitos permite ver lo ya depositado.
# ─────────────────────────────────────────────────────────────

class DepositoBancario(models.Model):
    ENTIDAD_PAGOFACIL = 'pagofacil'
    ENTIDAD_RAPIPAGO  = 'rapipago'
    ENTIDADES = [
        (ENTIDAD_PAGOFACIL, 'PagoFácil'),
        (ENTIDAD_RAPIPAGO,  'RapiPago'),
    ]

    entidad            = models.CharField(max_length=20, choices=ENTIDADES)
    fecha              = models.DateField(help_text="Fecha en que se realizó el depósito")

    # ── Composición del depósito (un cierre real suele mezclar los 3 orígenes
    # a la vez: parte efectivo, parte transferencia directa al banco, y a
    # veces una corrección de saldo a favor) ──
    monto_efectivo_fisico  = models.DecimalField(
                                 max_digits=12, decimal_places=2, default=Decimal('0'),
                                 help_text="Efectivo físico depositado en este registro")
    monto_ya_en_banco      = models.DecimalField(
                                 max_digits=12, decimal_places=2, default=Decimal('0'),
                                 help_text="Dinero que ya estaba en el banco (transferencias directas)")
    monto_saldo_plataforma = models.DecimalField(
                                 max_digits=12, decimal_places=2, default=Decimal('0'),
                                 help_text="Corrección/agregado manual al saldo a favor en la "
                                           "plataforma. Normalmente 0 — el saldo a favor ya se "
                                           "arrastra solo vía 'diferencia', no hace falta cargarlo "
                                           "cada ciclo. Completar solo para corregir un desvío.")
    monto              = models.DecimalField(
                             max_digits=12, decimal_places=2,
                             help_text="Monto total depositado (suma de los 3 componentes de arriba)")
    numero_comprobante = models.CharField(
                             max_length=100, blank=True,
                             help_text="Número de boleta o comprobante bancario")
    diferencia         = models.DecimalField(
                             max_digits=12, decimal_places=2, null=True, blank=True,
                             help_text="monto − pendiente de depositar en ese momento. "
                                       "Positivo = sobrante, negativo = faltante.")

    # ── Snapshot del cálculo al momento de este depósito (auditoría) ──
    # Se guardan además de 'diferencia' para que el historial muestre el
    # cálculo completo de cada depósito, no solo el resultado final.
    recaudado_pendiente_momento = models.DecimalField(
                             max_digits=12, decimal_places=2, null=True, blank=True,
                             help_text="Suma de recaudación del período cubierto, antes de "
                                       "descontar el saldo anterior.")
    saldo_anterior_momento      = models.DecimalField(
                             max_digits=12, decimal_places=2, null=True, blank=True,
                             help_text="Diferencia del depósito anterior (con signo) vigente "
                                       "al momento de registrar este depósito.")
    neto_a_depositar_momento    = models.DecimalField(
                             max_digits=12, decimal_places=2, null=True, blank=True,
                             help_text="Recaudado pendiente − saldo anterior: lo que había que "
                                       "depositar en este ciclo, antes de este depósito.")
    periodo_desde_momento       = models.DateField(null=True, blank=True)
    periodo_hasta_momento       = models.DateField(null=True, blank=True)

    observaciones      = models.TextField(blank=True)
    realizado_por      = models.ForeignKey(
                             Usuario, on_delete=models.SET_NULL,
                             null=True, related_name='depositos_bancarios')
    fecha_registro     = models.DateTimeField(auto_now_add=True,
                             help_text="Momento en que se cargó en el sistema")

    class Meta:
        ordering = ['-fecha', '-fecha_registro']
        verbose_name        = 'Depósito bancario'
        verbose_name_plural = 'Depósitos bancarios'

    def get_entidad_display_label(self):
        return dict(self.ENTIDADES).get(self.entidad, self.entidad)

    def __str__(self):
        return (
            f"Depósito {self.get_entidad_display()} "
            f"${self.monto} — {self.fecha:%d/%m/%Y}"
        )


def _ticket_deposito_path(instance, filename):
    return f'cobranzas/tickets_depositos/{instance.deposito_id}/{filename}'


class DepositoTicket(models.Model):
    """
    Comprobante (transferencia o depósito en efectivo) asociado a un
    DepositoBancario. Se carga por separado, después de registrar el
    depósito, vía el botón "Ver/editar ticket".
    """
    deposito           = models.OneToOneField(
                             DepositoBancario, on_delete=models.CASCADE,
                             related_name='ticket')
    imagen              = models.ImageField(
                             upload_to=_ticket_deposito_path, blank=True, null=True,
                             help_text="Foto o captura del comprobante")
    fecha_hora_ticket   = models.DateTimeField(
                             null=True, blank=True,
                             help_text="Fecha y hora que figura en el comprobante")
    monto_ticket        = models.DecimalField(
                             max_digits=12, decimal_places=2, null=True, blank=True,
                             help_text="Monto que figura en el comprobante (puede diferir del "
                                       "monto cargado en el depósito)")
    numero_operacion    = models.CharField(max_length=100, blank=True)
    banco               = models.CharField(max_length=100, blank=True)
    titular_nombre      = models.CharField(max_length=150, blank=True)
    titular_cuit        = models.CharField(max_length=30, blank=True)
    cuenta_origen       = models.CharField(
                             max_length=150, blank=True,
                             help_text="Ej: CA$ N° 4085782-3 071-4")
    destinatario        = models.CharField(
                             max_length=150, blank=True,
                             help_text="Solo transferencias: razón social/nombre del destinatario")
    cuenta_destino      = models.CharField(
                             max_length=150, blank=True,
                             help_text="Solo transferencias: CBU/cuenta destino")
    sucursal            = models.CharField(
                             max_length=150, blank=True,
                             help_text="Solo depósitos en efectivo: sucursal/terminal/dirección")
    concepto            = models.CharField(max_length=150, blank=True)
    estado              = models.CharField(
                             max_length=100, blank=True,
                             help_text="Ej: 'Depósito confirmado'")
    observaciones       = models.TextField(blank=True)
    cargado_por         = models.ForeignKey(
                             Usuario, on_delete=models.SET_NULL,
                             null=True, related_name='tickets_depositos')
    fecha_carga         = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Ticket depósito #{self.deposito_id}"


class RecaudacionDiaria(models.Model):
    ENTIDAD_PAGOFACIL = 'pagofacil'
    ENTIDAD_RAPIPAGO  = 'rapipago'
    ENTIDADES = [
        (ENTIDAD_PAGOFACIL, 'PagoFácil'),
        (ENTIDAD_RAPIPAGO,  'RapiPago'),
    ]
 
    entidad        = models.CharField(max_length=20, choices=ENTIDADES)
    fecha          = models.DateField(help_text="Fecha de la recaudación")
    monto          = models.DecimalField(
                         max_digits=12, decimal_places=2,
                         help_text="Monto recaudado en el día")
    cubierta_por   = models.ForeignKey(
                         'DepositoBancario', on_delete=models.SET_NULL,
                         null=True, blank=True, related_name='recaudaciones_cubiertas',
                         help_text="Depósito que saldó esta recaudación. "
                                   "NULL = todavía pendiente de depositar.")
    observaciones  = models.TextField(blank=True)
    registrado_por = models.ForeignKey(
                         'core.Usuario', on_delete=models.SET_NULL,
                         null=True, related_name='recaudaciones_registradas')
    fecha_registro = models.DateTimeField(
                         auto_now_add=True,
                         help_text="Momento en que se cargó en el sistema")
 
    class Meta:
        ordering = ['-fecha', '-fecha_registro']
        # Un registro por entidad por día (se puede modificar o eliminar si se
        # quiere permitir múltiples registros por día — ver nota en views_recaudaciones.py)
        unique_together = [('entidad', 'fecha')]
        verbose_name        = 'Recaudación diaria'
        verbose_name_plural = 'Recaudaciones diarias'
 
    def __str__(self):
        return (
            f"Recaudación {self.get_entidad_display()} "
            f"${self.monto} — {self.fecha:%d/%m/%Y}"
        )


# ─────────────────────────────────────────────────────────────
# GANANCIAS (adicionales)
#
# El "adicional" cobrado en cada ItemCobro (monto_adicional) es la
# ganancia propia del negocio, separada de lo que hay que depositar
# a PagoFácil/RapiPago. Se va acumulando en un pozo único (no se
# reinicia por ciclo, a diferencia de los depósitos) del que se
# retira plata para gastos/adelantos a empleados. GastoGanancia
# registra cada retiro: quién lo usó y para qué, para poder
# descontarlo del total ganado.
# ─────────────────────────────────────────────────────────────

class GastoGanancia(models.Model):
    fecha          = models.DateField(default=timezone.localdate,
                         help_text="Fecha en que se entregó/usó el dinero")
    persona        = models.CharField(
                         max_length=150,
                         help_text="Quién lo usó. Texto libre: puede ser un usuario del "
                                   "sistema o simplemente el nombre de una persona.")
    motivo         = models.CharField(max_length=300, help_text="Para qué se usó")
    monto          = models.DecimalField(max_digits=12, decimal_places=2)
    observaciones  = models.TextField(blank=True)
    registrado_por = models.ForeignKey(
                         'core.Usuario', on_delete=models.SET_NULL,
                         null=True, related_name='gastos_ganancias_registrados')
    fecha_registro = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-fecha', '-fecha_registro']
        verbose_name        = 'Gasto de ganancias'
        verbose_name_plural = 'Gastos de ganancias'

    def __str__(self):
        return f"Gasto ${self.monto} — {self.persona} — {self.fecha:%d/%m/%Y}"