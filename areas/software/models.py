from django.core.exceptions import ValidationError
from django.db import models
from core.models import Usuario, Cliente


# ─────────────────────────────────────────────────────────────
# VPS
# Servidores donde se alojan los servicios de software propios
# o de clientes.
# ─────────────────────────────────────────────────────────────

class VPS(models.Model):
    nombre    = models.CharField('Nombre / alias', max_length=100,
                    help_text='Ej: VPS Principal, VPS Clientes 1')
    proveedor = models.CharField(max_length=100,
                    help_text='Ej: Hostinger, DigitalOcean, AWS, Contabo')
    ip        = models.GenericIPAddressField('Dirección IP')

    # ── Plan contratado ──
    plan               = models.CharField(max_length=100, blank=True, help_text='Ej: KVM 1')
    fecha_vencimiento  = models.DateField('Fecha de vencimiento', null=True, blank=True)

    # ── Recursos del plan ──
    nucleos_cpu     = models.PositiveIntegerField('Núcleos de CPU', null=True, blank=True)
    memoria         = models.CharField('Memoria', max_length=30, blank=True, help_text='Ej: 4 GB')
    espacio_disco   = models.CharField('Espacio en disco', max_length=30, blank=True, help_text='Ej: 50 GB')
    ancho_banda     = models.CharField('Ancho de banda', max_length=30, blank=True, help_text='Ej: 4 TB')
    sistema_operativo = models.CharField('Sistema operativo', max_length=100, blank=True, help_text='Ej: Ubuntu 24.04 LTS')

    # ── Acceso ──
    usuario_ssh  = models.CharField('Nombre de usuario SSH', max_length=50, blank=True, default='root')
    acceso_ssh   = models.CharField('Comando de acceso', max_length=200, blank=True,
                       help_text='Ej: ssh root@85.209.92.238')

    notas     = models.TextField(blank=True)
    activa    = models.BooleanField(default=True)

    creado_por         = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True, blank=True,
                                            related_name='vps_creadas')
    fecha_alta          = models.DateTimeField(auto_now_add=True)
    modificado_por      = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True, blank=True,
                                             related_name='vps_modificadas')
    fecha_modificacion  = models.DateTimeField(auto_now=True)

    class Meta:
        ordering            = ['nombre']
        verbose_name        = 'VPS'
        verbose_name_plural = 'VPS'

    def __str__(self):
        return f"{self.nombre} — {self.proveedor} ({self.ip})"

    def vencida(self):
        if not self.fecha_vencimiento:
            return False
        from datetime import date
        return date.today() > self.fecha_vencimiento

    def proxima_a_vencer(self, dias=30):
        if not self.fecha_vencimiento:
            return False
        from datetime import date, timedelta
        return date.today() <= self.fecha_vencimiento <= date.today() + timedelta(days=dias)


# ─────────────────────────────────────────────────────────────
# SERVICIO SOFTWARE
# Catálogo de software propio que se despliega en las VPS
# (ej: Kaircam, Kai-Cart).
# ─────────────────────────────────────────────────────────────

class ServicioSoftware(models.Model):
    nombre      = models.CharField(max_length=100, unique=True)
    descripcion = models.TextField(blank=True)
    activo      = models.BooleanField(default=True)

    creado_por     = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True, blank=True,
                                        related_name='servicios_software_creados')
    fecha_alta     = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering            = ['nombre']
        verbose_name        = 'Servicio de software'
        verbose_name_plural = 'Servicios de software'

    def __str__(self):
        return self.nombre


# ─────────────────────────────────────────────────────────────
# INSTALACIÓN
# Una instancia concreta de un ServicioSoftware corriendo en
# una VPS determinada, para un cliente determinado.
# ─────────────────────────────────────────────────────────────

class Instalacion(models.Model):
    ESTADO_ACTIVO       = 'activo'
    ESTADO_INACTIVO     = 'inactivo'
    ESTADO_MANTENIMIENTO = 'mantenimiento'
    ESTADOS = [
        (ESTADO_ACTIVO,        'Activo'),
        (ESTADO_INACTIVO,      'Inactivo'),
        (ESTADO_MANTENIMIENTO, 'En mantenimiento'),
    ]

    vps      = models.ForeignKey(VPS, on_delete=models.PROTECT, related_name='instalaciones')
    servicio = models.ForeignKey(ServicioSoftware, on_delete=models.PROTECT, related_name='instalaciones')

    # Cliente: puede ser uno ya cargado en el sistema, o solo texto libre
    # si todavía no existe como Cliente formal.
    cliente       = models.ForeignKey(Cliente, on_delete=models.SET_NULL, null=True, blank=True,
                                       related_name='instalaciones_software')
    cliente_texto = models.CharField('Cliente (texto libre)', max_length=150, blank=True,
                                      help_text='Usar solo si el cliente no está cargado en el sistema')

    dominio = models.CharField(max_length=200, blank=True)
    puerto  = models.PositiveIntegerField(null=True, blank=True)

    ruta_proyecto = models.CharField('Ruta del proyecto', max_length=300, blank=True,
                        help_text='Ej: /home/deploy/kai-cart-clientex')
    ruta_service  = models.CharField('Ruta del .service', max_length=300, blank=True,
                        help_text='Ej: /etc/systemd/system/kai-cart-clientex.service')
    ruta_conf     = models.CharField('Ruta del .conf', max_length=300, blank=True,
                        help_text='Ej: /etc/nginx/sites-available/kai-cart-clientex.conf')

    estado      = models.CharField(max_length=15, choices=ESTADOS, default=ESTADO_ACTIVO)
    descripcion = models.TextField(blank=True)

    comandos = models.TextField('Comandos de actualización', blank=True,
                   help_text='Comandos para actualizar esta instalación puntualmente '
                             '(ej: cd /home/deploy/proyecto && git pull && systemctl restart proyecto)')

    creado_por          = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True, blank=True,
                                             related_name='instalaciones_creadas')
    fecha_alta          = models.DateTimeField(auto_now_add=True)
    modificado_por      = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True, blank=True,
                                             related_name='instalaciones_modificadas')
    fecha_modificacion  = models.DateTimeField(auto_now=True)

    class Meta:
        ordering            = ['-fecha_alta']
        verbose_name        = 'Instalación'
        verbose_name_plural = 'Instalaciones'

    def __str__(self):
        return f"{self.servicio} en {self.vps} — {self.get_cliente_display()}"

    def get_cliente_display(self):
        if self.cliente_id:
            return self.cliente.get_nombre_display()
        return self.cliente_texto or 'Sin cliente'

    def get_url_dominio(self):
        """Dominio normalizado a URL completa (para el QR y links directos)."""
        dominio = self.dominio.strip()
        if not dominio:
            return ''
        if dominio.startswith(('http://', 'https://')):
            return dominio
        return f'https://{dominio}'

    def clean(self):
        # El FK a Cliente, si está cargado, tiene prioridad: evitamos
        # que quede texto libre "colgado" que nunca se muestra.
        if self.cliente_id and self.cliente_texto:
            self.cliente_texto = ''


# ─────────────────────────────────────────────────────────────
# SCRIPT
# Biblioteca de scripts/herramientas de automatización (apertura
# de puertos, deploy de un servicio nuevo, actualización masiva,
# etc). Solo almacenamiento: la ejecución se hace manualmente en
# la VPS, el sistema no se conecta por SSH.
# ─────────────────────────────────────────────────────────────

def _script_archivo_path(instance, filename):
    return f'software/scripts/{filename}'


class Script(models.Model):
    # Categorías sugeridas por defecto. No son las únicas: el campo es
    # texto libre para que se puedan agregar nuevas sobre la marcha
    # (ver get_todas_categorias en views_scripts.py, que las combina
    # con las que ya estén en uso en la DB).
    CATEGORIA_OTRO = 'Otro'
    CATEGORIAS_SUGERIDAS = [
        'Apertura de puertos',
        'Deploy de servicio nuevo',
        'Actualización de servicio',
        CATEGORIA_OTRO,
    ]

    nombre    = models.CharField(max_length=150)
    categoria = models.CharField(max_length=50, default=CATEGORIA_OTRO)

    # Opcional: script asociado a un servicio del catálogo
    # (ej: script para actualizar Kai-Cart en todos los clientes que lo usan).
    servicio = models.ForeignKey(ServicioSoftware, on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='scripts')

    # Opcional: VPS específica a la que aplica. Si queda vacío, el script
    # sirve para cualquier VPS (ej: abrir puertos, es genérico).
    vps = models.ForeignKey(VPS, on_delete=models.SET_NULL, null=True, blank=True,
                             related_name='scripts', verbose_name='VPS específica')

    descripcion = models.TextField(blank=True)
    contenido   = models.TextField(blank=True, help_text='Contenido del script (bash, etc.)')
    archivo     = models.FileField(upload_to=_script_archivo_path, blank=True, null=True,
                                    help_text='Opcional: subir el archivo original')

    creado_por          = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True, blank=True,
                                             related_name='scripts_creados')
    fecha_creacion       = models.DateTimeField(auto_now_add=True)
    modificado_por       = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True, blank=True,
                                              related_name='scripts_modificados')
    fecha_modificacion   = models.DateTimeField(auto_now=True)

    class Meta:
        ordering            = ['categoria', 'nombre']
        verbose_name        = 'Script'
        verbose_name_plural = 'Scripts'

    def __str__(self):
        return f"{self.nombre} ({self.categoria})"

    def clean(self):
        if not self.contenido and not self.archivo:
            raise ValidationError('Cargá el contenido del script o subí un archivo.')
        if not self.categoria.strip():
            raise ValidationError('La categoría no puede estar vacía.')

    def save(self, *args, **kwargs):
        self.categoria = self.categoria.strip() or self.CATEGORIA_OTRO
        super().save(*args, **kwargs)
