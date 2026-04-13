from django.db import models
from django.utils import timezone
from core.models import Usuario


# ─────────────────────────────────────────────────────────────
# SERVICIO
# ─────────────────────────────────────────────────────────────

class Servicio(models.Model):
    codigo      = models.CharField(max_length=20, unique=True)
    descripcion = models.CharField(max_length=300)
    monto       = models.DecimalField(max_digits=12, decimal_places=2)
    activo      = models.BooleanField(default=True)
    proveedor   = models.CharField(max_length=100, blank=True)

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
