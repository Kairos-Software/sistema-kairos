from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views import View

from core.permisos import chequear_permiso
from .forms import InstalacionForm
from .models import VPS, ServicioSoftware, Instalacion


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

        paginator = Paginator(qs, 10)
        instalaciones = paginator.get_page(request.GET.get('page', 1))

        context = {
            'instalaciones':   instalaciones,
            'q':               q,
            'filtro_vps':      vps_id or '',
            'filtro_servicio': servicio_id or '',
            'filtro_estado':   estado or '',
            'filtro_puerto':   puerto,
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
