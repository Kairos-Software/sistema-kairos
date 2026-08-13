from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.db.models import ProtectedError, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views import View

from core.permisos import chequear_permiso
from .forms import VPSForm
from .models import VPS


class GestionVpsView(LoginRequiredMixin, View):
    def get(self, request):
        if not chequear_permiso(request.user, 'ver_vps'):
            return render(request, 'software/gestion_vps.html', {'sin_permiso': True}, status=403)

        qs = VPS.objects.all()
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(nombre__icontains=q) | Q(proveedor__icontains=q) | Q(ip__icontains=q))

        activa = request.GET.get('activa')
        if activa in ('true', 'false'):
            qs = qs.filter(activa=(activa == 'true'))

        paginator = Paginator(qs, 10)
        vps_page = paginator.get_page(request.GET.get('page', 1))

        context = {
            'vps_list':       vps_page,
            'q':              q,
            'filtro_activa':  activa,
            'puede_crear':    chequear_permiso(request.user, 'crear_vps'),
            'puede_editar':   chequear_permiso(request.user, 'editar_vps'),
            'puede_eliminar': chequear_permiso(request.user, 'eliminar_vps'),
            'sin_permiso':    False,
        }
        return render(request, 'software/gestion_vps.html', context)


class VpsCrearEditarAjax(LoginRequiredMixin, View):
    def post(self, request):
        pk = request.POST.get('pk')
        if pk:
            if not chequear_permiso(request.user, 'editar_vps'):
                return JsonResponse({'error': 'Sin permiso'}, status=403)
            vps = get_object_or_404(VPS, pk=pk)
            form = VPSForm(request.POST, instance=vps)
        else:
            if not chequear_permiso(request.user, 'crear_vps'):
                return JsonResponse({'error': 'Sin permiso'}, status=403)
            form = VPSForm(request.POST)

        if form.is_valid():
            vps = form.save(commit=False)
            if not pk:
                vps.creado_por = request.user
            else:
                vps.modificado_por = request.user
            vps.save()
            return JsonResponse({'success': True, 'vps': {
                'id':        vps.pk,
                'nombre':    vps.nombre,
                'proveedor': vps.proveedor,
                'ip':        vps.ip,
                'notas':     vps.notas,
                'activa':    vps.activa,
            }})
        return JsonResponse({'success': False, 'errors': form.errors}, status=400)


class VpsEliminarAjax(LoginRequiredMixin, View):
    def post(self, request):
        if not chequear_permiso(request.user, 'eliminar_vps'):
            return JsonResponse({'error': 'Sin permiso'}, status=403)
        pk = request.POST.get('pk')
        vps = get_object_or_404(VPS, pk=pk)
        try:
            vps.delete()
            return JsonResponse({'success': True})
        except ProtectedError:
            return JsonResponse({
                'success': False,
                'error': (
                    f'No se puede eliminar "{vps.nombre}" porque tiene instalaciones registradas. '
                    f'Eliminá primero esas instalaciones o reasignalas a otra VPS.'
                )
            }, status=400)
