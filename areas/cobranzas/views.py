from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View
from django.core.paginator import Paginator
from django.db.models import Q

from core.permisos import chequear_permiso
from .models import Servicio
from .forms import ServicioForm


class InicioCobranzasView(LoginRequiredMixin, View):
    """Página de inicio del módulo Cobranzas"""
    def get(self, request):
        return render(request, 'cobranzas/inicio_cobranzas.html')


class GestionServiciosView(LoginRequiredMixin, View):
    def get(self, request):
        if not chequear_permiso(request.user, 'ver_servicios'):
            return render(request, 'cobranzas/gestion_servicios.html', {
                'sin_permiso': True,
            }, status=403)

        qs = Servicio.objects.all()
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(codigo__icontains=q) |
                Q(descripcion__icontains=q) |
                Q(proveedor__icontains=q)
            )

        # Filtro por monto exacto
        monto = request.GET.get('monto', '').strip()
        if monto:
            try:
                monto = float(monto)
                qs = qs.filter(monto=monto)
            except ValueError:
                pass

        activo = request.GET.get('activo')
        if activo in ('true', 'false'):
            qs = qs.filter(activo=(activo == 'true'))

        paginator = Paginator(qs, 25)
        servicios = paginator.get_page(request.GET.get('page', 1))

        context = {
            'servicios': servicios,
            'q': q,
            'filtro_activo': activo,
            'puede_crear': chequear_permiso(request.user, 'crear_servicios'),
            'puede_editar': chequear_permiso(request.user, 'editar_servicios'),
            'puede_eliminar': chequear_permiso(request.user, 'eliminar_servicios'),
            'sin_permiso': False,
        }
        return render(request, 'cobranzas/gestion_servicios.html', context)


class ServicioCrearEditarAjax(LoginRequiredMixin, View):
    def post(self, request):
        pk = request.POST.get('pk')
        if pk:
            if not chequear_permiso(request.user, 'editar_servicios'):
                return JsonResponse({'error': 'Sin permiso'}, status=403)
            servicio = get_object_or_404(Servicio, pk=pk)
            form = ServicioForm(request.POST, instance=servicio)
        else:
            if not chequear_permiso(request.user, 'crear_servicios'):
                return JsonResponse({'error': 'Sin permiso'}, status=403)
            form = ServicioForm(request.POST)

        if form.is_valid():
            servicio = form.save(commit=False)
            if not pk:
                servicio.creado_por = request.user
            else:
                servicio.modificado_por = request.user
            servicio.save()
            return JsonResponse({'success': True, 'servicio': {
                'id': servicio.pk,
                'codigo': servicio.codigo,
                'descripcion': servicio.descripcion,
                'monto': str(servicio.monto),
                'activo': servicio.activo,
                'proveedor': servicio.proveedor,
            }})
        return JsonResponse({'success': False, 'errors': form.errors}, status=400)


class ServicioEliminarAjax(LoginRequiredMixin, View):
    def post(self, request):
        if not chequear_permiso(request.user, 'eliminar_servicios'):
            return JsonResponse({'error': 'Sin permiso'}, status=403)
        pk = request.POST.get('pk')
        servicio = get_object_or_404(Servicio, pk=pk)
        servicio.delete()
        return JsonResponse({'success': True})


class ServicioActivarAjax(LoginRequiredMixin, View):
    def post(self, request):
        if not chequear_permiso(request.user, 'editar_servicios'):
            return JsonResponse({'error': 'Sin permiso'}, status=403)
        pk = request.POST.get('pk')
        activo = request.POST.get('activo') == 'true'
        servicio = get_object_or_404(Servicio, pk=pk)
        servicio.activo = activo
        servicio.modificado_por = request.user
        servicio.save()
        return JsonResponse({'success': True, 'activo': servicio.activo})