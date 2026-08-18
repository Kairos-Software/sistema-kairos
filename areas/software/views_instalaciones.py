import qrcode
import qrcode.image.svg

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.db.models import F, Q
from django.db.models.functions import Coalesce, Lower
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views import View

from core.permisos import chequear_permiso
from .forms import InstalacionForm
from .models import VPS, ServicioSoftware, Instalacion

# ─────────────────────────────────────────────────────────────
# Ordenamiento — se resuelve en la base de datos (order_by), NO en
# el cliente. Es imprescindible porque la lista está paginada: un
# sort en JS solo reordena las 10 filas de la página visible, así
# que por ejemplo "puerto ascendente" quedaba roto en cuanto había
# más de una página (el orden real seguía siendo el de alta, no el
# de puerto). Los campos numéricos (puerto) no tienen ambigüedad de
# collation entre motores, así que ordenar en DB es seguro acá.
# Los blancos siempre quedan al final, sea cual sea la dirección.
# ─────────────────────────────────────────────────────────────

_CLIENTE_ORDEN = Coalesce(
    'cliente__nombre_comercial', 'cliente__razon_social',
    'cliente__nombre', 'cliente_texto',
)

ORDENES_INSTALACIONES = {
    'fecha_desc':    ('-fecha_alta',),
    'fecha_asc':     ('fecha_alta',),
    'puerto_asc':    (F('puerto').asc(nulls_last=True),),
    'puerto_desc':   (F('puerto').desc(nulls_last=True),),
    'servicio_asc':  (Lower('servicio__nombre'),),
    'servicio_desc': (Lower('servicio__nombre').desc(),),
    'vps_asc':       (Lower('vps__nombre'),),
    'vps_desc':      (Lower('vps__nombre').desc(),),
    'dominio_asc':   (Lower('dominio'),),
    'dominio_desc':  (Lower('dominio').desc(),),
    'estado_asc':    ('estado',),
    'estado_desc':   ('-estado',),
    'cliente_asc':   (Lower(_CLIENTE_ORDEN),),
    'cliente_desc':  (Lower(_CLIENTE_ORDEN).desc(),),
}


class GestionInstalacionesView(LoginRequiredMixin, View):
    def get(self, request):
        if not chequear_permiso(request.user, 'ver_instalaciones'):
            return render(request, 'software/gestion_instalaciones.html', {'sin_permiso': True}, status=403)

        qs = Instalacion.objects.select_related('vps', 'servicio', 'cliente')
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(dominio__icontains=q) |
                Q(cliente_texto__icontains=q) |
                Q(cliente__nombre__icontains=q) |
                Q(cliente__apellido__icontains=q) |
                Q(cliente__razon_social__icontains=q) |
                Q(cliente__nombre_comercial__icontains=q) |
                Q(vps__nombre__icontains=q) |
                Q(servicio__nombre__icontains=q)
            )

        vps_id = request.GET.get('vps')
        if vps_id:
            qs = qs.filter(vps_id=vps_id)

        servicio_id = request.GET.get('servicio')
        if servicio_id:
            qs = qs.filter(servicio_id=servicio_id)

        estado = request.GET.get('estado')
        if estado:
            qs = qs.filter(estado=estado)

        puerto = request.GET.get('puerto', '').strip()
        if puerto:
            try:
                qs = qs.filter(puerto=int(puerto))
            except ValueError:
                pass

        orden = request.GET.get('orden') or 'fecha_desc'
        if orden not in ORDENES_INSTALACIONES:
            orden = 'fecha_desc'
        qs = qs.order_by(*ORDENES_INSTALACIONES[orden])

        paginator = Paginator(qs, 10)
        instalaciones = paginator.get_page(request.GET.get('page', 1))

        context = {
            'instalaciones':   instalaciones,
            'q':               q,
            'filtro_vps':      vps_id or '',
            'filtro_servicio': servicio_id or '',
            'filtro_estado':   estado or '',
            'filtro_puerto':   puerto,
            'orden':           orden,
            'todas_vps':       VPS.objects.all(),
            'todos_servicios': ServicioSoftware.objects.all(),
            'estados':         Instalacion.ESTADOS,
            'puede_crear':     chequear_permiso(request.user, 'crear_instalaciones'),
            'puede_editar':    chequear_permiso(request.user, 'editar_instalaciones'),
            'puede_eliminar':  chequear_permiso(request.user, 'eliminar_instalaciones'),
            'sin_permiso':     False,
        }
        return render(request, 'software/gestion_instalaciones.html', context)


class InstalacionCrearEditarAjax(LoginRequiredMixin, View):
    def post(self, request):
        pk = request.POST.get('pk')
        if pk:
            if not chequear_permiso(request.user, 'editar_instalaciones'):
                return JsonResponse({'error': 'Sin permiso'}, status=403)
            instalacion = get_object_or_404(Instalacion, pk=pk)
            form = InstalacionForm(request.POST, instance=instalacion)
        else:
            if not chequear_permiso(request.user, 'crear_instalaciones'):
                return JsonResponse({'error': 'Sin permiso'}, status=403)
            form = InstalacionForm(request.POST)

        if form.is_valid():
            instalacion = form.save(commit=False)
            if not pk:
                instalacion.creado_por = request.user
            else:
                instalacion.modificado_por = request.user
            instalacion.full_clean()
            instalacion.save()
            return JsonResponse({'success': True, 'instalacion': {
                'id':             instalacion.pk,
                'vps':            instalacion.vps.nombre,
                'servicio':       instalacion.servicio.nombre,
                'cliente':        instalacion.get_cliente_display(),
                'dominio':        instalacion.dominio,
                'puerto':         instalacion.puerto,
                'ruta_proyecto':  instalacion.ruta_proyecto,
                'ruta_service':   instalacion.ruta_service,
                'ruta_conf':      instalacion.ruta_conf,
                'estado':         instalacion.estado,
                'estado_display': instalacion.get_estado_display(),
                'descripcion':    instalacion.descripcion,
                'comandos':       instalacion.comandos,
            }})
        return JsonResponse({'success': False, 'errors': form.errors}, status=400)


class InstalacionEliminarAjax(LoginRequiredMixin, View):
    def post(self, request):
        if not chequear_permiso(request.user, 'eliminar_instalaciones'):
            return JsonResponse({'error': 'Sin permiso'}, status=403)
        pk = request.POST.get('pk')
        instalacion = get_object_or_404(Instalacion, pk=pk)
        instalacion.delete()
        return JsonResponse({'success': True})


class InstalacionQrView(LoginRequiredMixin, View):
    """
    QR (SVG) que apunta directo al dominio guardado en la instalación.
    Se genera al vuelo a partir de `dominio` — no se persiste como imagen,
    así nunca queda desactualizado si el dominio cambia.
    """
    def get(self, request, pk):
        if not chequear_permiso(request.user, 'ver_instalaciones'):
            return JsonResponse({'error': 'Sin permiso'}, status=403)
        instalacion = get_object_or_404(Instalacion, pk=pk)
        url = instalacion.get_url_dominio()
        if not url:
            raise Http404('Esta instalación no tiene dominio cargado.')

        imagen = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage, box_size=10)
        response = HttpResponse(content_type='image/svg+xml')
        imagen.save(response)
        return response
