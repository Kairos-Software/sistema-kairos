from django.db import models
from core.models import Usuario


class Servicio(models.Model):
    codigo = models.CharField(max_length=20, unique=True)
    descripcion = models.CharField(max_length=300)
    monto = models.DecimalField(max_digits=12, decimal_places=2)
    activo = models.BooleanField(default=True)
    proveedor = models.CharField(max_length=100, blank=True)

    creado_por = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True, blank=True, related_name='servicios_creados')
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    modificado_por = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True, blank=True, related_name='servicios_modificados')
    fecha_modificacion = models.DateTimeField(auto_now=True)

    class Meta:
        # Orden alfanumérico real por código
        ordering = ['codigo']

    def __str__(self):
        return f"{self.codigo} - {self.descripcion[:40]}"
    

# ─────────────────────────────────────────────────────────────
# AGREGAR al final de models.py (después de la clase Servicio)
# ─────────────────────────────────────────────────────────────

class Cobro(models.Model):
    """
    Cabecera de una sesión de cobro.
    Agrupa varios ítems (boletas) y varios pagos.
    """
    ESTADO_ABIERTO  = 'abierto'
    ESTADO_CERRADO  = 'cerrado'
    ESTADO_ANULADO  = 'anulado'
    ESTADOS = [
        (ESTADO_ABIERTO,  'Abierto'),
        (ESTADO_CERRADO,  'Cerrado'),
        (ESTADO_ANULADO,  'Anulado'),
    ]

    estado          = models.CharField(max_length=10, choices=ESTADOS, default=ESTADO_ABIERTO)
    fecha_creacion  = models.DateTimeField(auto_now_add=True)
    fecha_cierre    = models.DateTimeField(null=True, blank=True)
    creado_por      = models.ForeignKey(
        'core.Usuario', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='cobros_creados'
    )
    observaciones   = models.TextField(blank=True)

    class Meta:
        ordering = ['-fecha_creacion']

    def __str__(self):
        return f"Cobro #{self.pk} — {self.get_estado_display()} — {self.fecha_creacion:%d/%m/%Y %H:%M}"

    # ── helpers ──────────────────────────────────────────────

    def total_adicionales(self):
        """Suma de todos los montos adicionales (nuestra ganancia)."""
        from django.db.models import Sum
        return self.items.aggregate(t=Sum('monto_adicional'))['t'] or 0

    def total_boletas(self):
        """Suma de todos los montos de los servicios (valor de las facturas)."""
        from django.db.models import Sum
        return self.items.aggregate(t=Sum('monto_servicio'))['t'] or 0

    def total_general(self):
        """Total a cobrar al cliente (boletas + adicionales)."""
        return self.total_boletas() + self.total_adicionales()

    def total_pagado(self):
        """Suma de todos los pagos registrados."""
        from django.db.models import Sum
        return self.pagos.aggregate(t=Sum('monto'))['t'] or 0


class ItemCobro(models.Model):
    """
    Una boleta/servicio dentro de un Cobro.
    Guarda el monto del servicio en el momento del cobro (snapshot),
    por si el servicio cambia de precio después.
    """
    CANAL_PAGOFACIL    = 'pagofacil'
    CANAL_RAPIPAGO     = 'rapipago'
    CANAL_OTRO         = 'otro'
    CANALES = [
        (CANAL_PAGOFACIL, 'Pago Fácil'),
        (CANAL_RAPIPAGO,  'Rapipago'),
        (CANAL_OTRO,      'Otro'),
    ]

    cobro           = models.ForeignKey(Cobro, on_delete=models.CASCADE, related_name='items')
    servicio        = models.ForeignKey(Servicio, on_delete=models.PROTECT, related_name='cobros')
    monto_servicio  = models.DecimalField(max_digits=12, decimal_places=2,
                                          help_text="Snapshot del monto del servicio al momento del cobro")
    monto_adicional = models.DecimalField(max_digits=12, decimal_places=2, default=0,
                                          help_text="Cargo adicional (nuestra ganancia)")
    canal           = models.CharField(max_length=20, choices=CANALES, default=CANAL_PAGOFACIL)
    orden           = models.PositiveSmallIntegerField(default=0,
                                                       help_text="Orden de carga en el carrito")

    class Meta:
        ordering = ['orden', 'pk']

    def __str__(self):
        return f"{self.servicio.codigo} — ${self.monto_servicio} + ${self.monto_adicional}"

    def subtotal(self):
        return self.monto_servicio + self.monto_adicional


class PagoCobro(models.Model):
    """
    Registra cómo se pagó (o parte de) un Cobro.
    Un cobro puede tener varios pagos con distintos métodos.
    Ej: $7000 en efectivo + $3000 en transferencia.
    """
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