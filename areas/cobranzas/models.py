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