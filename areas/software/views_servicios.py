from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.db.models import ProtectedError, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views import View

from core.permisos import chequear_permiso
from .forms import ServicioSoftwareForm
from .models import ServicioSoftware


class GestionServiciosSoftwareView(LoginRequiredMixin, View):
    def get(self, request):
        if not chequear_permiso(request.user, 'ver_servicios_software'):
            return render(request, 'software/gestion_servicios.html', {'sin_permiso': True}, status=403)

        qs = ServicioSoftware.objects.all()
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(nombre__icontains=q) | Q(descripcion__icontains=q))

        activo = request.GET.get('activo')
        if activo in ('true', 'false'):
            qs = qs.filter(activo=(activo == 'true'))

        paginator = Paginator(qs, 10)
        servicios = paginator.get_page(request.GET.get('page', 1))

        context = {
            'servicios':      servicios,
            'q':              q,
            'filtro_activo':  activo,
            'puede_crear':    chequear_permiso(request.user, 'crear_servicios_software'),
            'puede_editar':   chequear_permiso(request.user, 'editar_servicios_software'),
            'puede_eliminar': chequear_permiso(request.user, 'eliminar_servicios_software'),
            'sin_permiso':    False,
        }
        return render(request, 'software/gestion_servicios.html', context)


class ServicioSoftwareCrearEditarAjax(LoginRequiredMixin, View):
    def post(self, request):
        pk = request.POST.get('pk')
        if pk:
            if not chequear_permiso(request.user, 'editar_servicios_software'):
                return JsonResponse({'error': 'Sin permiso'}, status=403)
            servicio = get_object_or_404(ServicioSoftware, pk=pk)
            form = ServicioSoftwareForm(request.POST, instance=servicio)
        else:
            if not chequear_permiso(request.user, 'crear_servicios_software'):
                return JsonResponse({'error': 'Sin permiso'}, status=403)
            form = ServicioSoftwareForm(request.POST)

        if form.is_valid():
            servicio = form.save(commit=False)
            if not pk:
                servicio.creado_por = request.user
            servicio.save()
            return JsonResponse({'success': True, 'servicio': {
                'id':          servicio.pk,
                'nombre':      servicio.nombre,
                'descripcion': servicio.descripcion,
                'activo':      servicio.activo,
            }})
        return JsonResponse({'success': False, 'errors': form.errors}, status=400)


class ServicioSoftwareEliminarAjax(LoginRequiredMixin, View):
    def post(self, request):
        if not chequear_permiso(request.user, 'eliminar_servicios_software'):
            return JsonResponse({'error': 'Sin permiso'}, status=403)
        pk = request.POST.get('pk')
        servicio = get_object_or_404(ServicioSoftware, pk=pk)
        try:
            servicio.delete()
            return JsonResponse({'success': True})
        except ProtectedError:
            return JsonResponse({
                'success': False,
                'error': (
                    f'No se puede eliminar "{servicio.nombre}" porque tiene instalaciones registradas.'
                )
            }, status=400)
