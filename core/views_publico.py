import time

from django.db.models import Q
from django.http import Http404
from django.shortcuts import render
from django.views import View
from django.views.generic import TemplateView

from .models import Cliente


# ══════════════════════════════════════════════════════════════════
#  CONTENIDO DE LAS ÁREAS PÚBLICAS
#  Cada área es una página propia (/areas/<slug>/) con su info.
# ══════════════════════════════════════════════════════════════════

AREAS = {
    'cobranzas': {
        'slug': 'cobranzas',
        'nombre': 'Cobranzas',
        'titular': 'Pagá todo en un solo lugar',
        'intro': 'Nuestro centro de pagos presencial: servicios, impuestos, '
                 'recargas y transferencias, con comprobante en el momento y '
                 'atención cara a cara.',
        'destacado': 'Ya sos cliente y querés ver tus servicios contratados. '
                     'Podés consultarlos con tu DNI o tu número de cliente.',
        'features': [
            ('Pago Fácil y Rapipago',
             'Cobramos las boletas de las dos redes: luz, agua, gas, teléfono, '
             'tarjetas, AFIP, rentas y municipales.'),
            ('Western Union',
             'Envío y recepción de giros de dinero, con la mejor cotización del día.'),
            ('Recargas y SUBE',
             'Carga de crédito para celulares, transporte y tarjetas prepagas.'),
            ('Extracciones de efectivo',
             'Retirá plata de tu cuenta sin ir al banco ni al cajero.'),
            ('Comprobante al instante',
             'Te llevás el ticket de cada operación en el momento, sin esperas.'),
            ('Atención personal',
             'Alguien que te explica y te ayuda, no una máquina.'),
        ],
        'cta_titulo': '¿Ya sos cliente de Cobranzas?',
        'cta_texto': 'Consultá los servicios que tenés contratados y su estado.',
        'cta_label': 'Consultá tu cuenta',
        'cta_es_consulta': True,
    },
    'software': {
        'slug': 'software',
        'nombre': 'Software',
        'titular': 'Software que se adapta a tu negocio',
        'intro': 'Desarrollamos sistemas a medida, aplicaciones web y móviles, '
                 'y plataformas de gestión pensadas para cómo trabajás vos.',
        'destacado': 'Trabajamos de punta a punta: relevamiento, desarrollo, '
                     'puesta en marcha y mantenimiento continuo.',
        'features': [
            ('Sistemas ERP y CRM',
             'Gestión de ventas, stock, compras, clientes y facturación en un solo lugar.'),
            ('Aplicaciones web',
             'Paneles, portales y herramientas internas accesibles desde cualquier navegador.'),
            ('Apps para iOS y Android',
             'Aplicaciones móviles nativas y multiplataforma para tus clientes o tu equipo.'),
            ('Integración de APIs',
             'Conectamos tu operación con medios de pago, AFIP, logística y otros servicios.'),
            ('Arquitectura y consultoría',
             'Te ayudamos a decidir qué construir, con qué tecnología y en qué orden.'),
            ('Mantenimiento y soporte',
             'Acompañamos el sistema después del lanzamiento: mejoras, ajustes y respaldo.'),
        ],
        'plataformas': [
            ('Kai-Cart', 'Tienda online lista para vender, con catálogo, carrito y medios de pago.'),
            ('Kaircam', 'Monitoreo y gestión de cámaras de seguridad desde el celular.'),
        ],
        'cta_titulo': '¿Tenés un proyecto en mente?',
        'cta_texto': 'Contanos qué necesitás y armamos una propuesta sin cargo.',
        'cta_label': 'Escribinos',
        'cta_es_consulta': False,
    },
    'internet': {
        'slug': 'internet',
        'nombre': 'Internet',
        'titular': 'Conexión estable, soporte local',
        'intro': 'Conectividad de alta velocidad y redes WiFi robustas para tu '
                 'casa o tu empresa, instaladas y sostenidas por gente de acá.',
        'destacado': 'Nada de call centers eternos: si algo falla, hablás con '
                     'alguien que conoce tu instalación.',
        'features': [
            ('Fibra óptica',
             'Velocidad simétrica y baja latencia para trabajar, estudiar o transmitir.'),
            ('WiFi mesh',
             'Cobertura pareja en toda la casa o la oficina, sin zonas muertas.'),
            ('Enlaces dedicados',
             'Ancho de banda garantizado para empresas que no pueden quedarse sin servicio.'),
            ('VPN y redes privadas',
             'Conectá sucursales y equipos remotos de forma segura.'),
            ('Optimización de ancho de banda',
             'Priorizamos lo importante para que la conexión rinda cuando más la necesitás.'),
            ('Instalación y configuración',
             'Dejamos todo funcionando y te explicamos cómo sacarle el jugo.'),
        ],
        'cta_titulo': '¿Querés mejorar tu conexión?',
        'cta_texto': 'Contanos dónde estás y qué necesitás, y vemos la mejor opción.',
        'cta_label': 'Escribinos',
        'cta_es_consulta': False,
    },
}

AREAS_ORDEN = ['cobranzas', 'software', 'internet']

OTROS_SERVICIOS = [
    'Informática', 'Cámaras de seguridad', 'Telefonía', 'Electricidad',
    'Construcción', 'Diseño web', 'Diseño gráfico', 'Impresión 3D', 'Refrigeración',
]

# Contacto — REEMPLAZAR por los datos reales antes de publicar.
CONTACTO = {
    'whatsapp_display': '+54 9 11 0000-0000',
    'whatsapp_link': 'https://wa.me/5491100000000',
    'email': 'hola@grupokairosarg.com',
}


def _nav(activo=None):
    return {
        'nav_areas': [AREAS[s] for s in AREAS_ORDEN],
        'nav_activo': activo,
        'contacto': CONTACTO,
    }


class HomeView(TemplateView):
    template_name = 'core/publico/home.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(_nav('inicio'))
        ctx['otros_servicios'] = OTROS_SERVICIOS
        return ctx


class AreaView(View):
    def get(self, request, slug):
        area = AREAS.get(slug)
        if area is None:
            raise Http404('Área no encontrada')
        ctx = {'area': area}
        ctx.update(_nav(slug))
        return render(request, 'core/publico/area.html', ctx)


class ConsultaClienteView(View):
    template_name = 'core/publico/consulta.html'

    def _ctx(self, extra=None):
        ctx = _nav('consulta')
        if extra:
            ctx.update(extra)
        return ctx

    def get(self, request):
        return render(request, self.template_name, self._ctx())

    def post(self, request):
        # Anti-fuerza-bruta mínimo: honeypot + pequeña demora.
        if request.POST.get('empresa', '').strip():
            return render(request, self.template_name,
                          self._ctx({'error': 'No pudimos procesar la consulta.'}))
        time.sleep(0.4)

        dato = request.POST.get('dato', '').strip()

        if not dato:
            return render(request, self.template_name, self._ctx({
                'dato': dato,
                'error': 'Ingresá tu DNI o tu número de cliente.',
            }))

        cliente = (
            Cliente.objects
            .filter(Q(dni__iexact=dato) | Q(codigo__iexact=dato))
            .prefetch_related('servicios_contratados')
            .first()
        )

        if cliente is None:
            return render(request, self.template_name, self._ctx({
                'dato': dato,
                'error': 'No encontramos una cuenta con ese dato. '
                         'Revisá tu DNI o tu número de cliente.',
            }))

        grupos = {}
        for s in cliente.servicios_contratados.all():
            grupos.setdefault(s.get_area_display(), []).append({
                'nombre': s.nombre,
                'descripcion': s.descripcion,
                'identificador': s.identificador,
                'estado': s.estado,
                'estado_display': s.get_estado_display(),
            })

        from areas.software.models import Instalacion
        for inst in Instalacion.objects.filter(cliente=cliente).select_related('servicio'):
            grupos.setdefault('Software', []).append({
                'nombre': inst.servicio.nombre,
                'descripcion': inst.descripcion,
                'identificador': inst.dominio,
                'estado': inst.estado,
                'estado_display': inst.get_estado_display(),
            })

        return render(request, self.template_name, self._ctx({
            'cliente': cliente,
            'grupos': sorted(grupos.items()),
            'consultado': True,
        }))
