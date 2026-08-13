from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.db.models import Q
from django.db.models.functions import Lower
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views import View

from core.permisos import chequear_permiso
from .forms import ScriptForm
from .models import VPS, ServicioSoftware, Script


def get_todas_categorias():
    """Categorías sugeridas por defecto + las que ya estén en uso en la DB."""
    en_uso = Script.objects.exclude(categoria='').values_list('categoria', flat=True).distinct()
    todas = set(Script.CATEGORIAS_SUGERIDAS) | set(en_uso)
    return sorted(todas)


# Ordenamiento resuelto en la DB (ver nota en views_instalaciones.py).
ORDENES_SCRIPTS = {
    'nombre_asc':      (Lower('nombre'),),
    'nombre_desc':     (Lower('nombre').desc(),),
    'categoria_asc':   (Lower('categoria'), Lower('nombre')),
    'categoria_desc':  (Lower('categoria').desc(), Lower('nombre')),
    'servicio_asc':    (Lower('servicio__nombre').asc(nulls_last=True),),
    'servicio_desc':   (Lower('servicio__nombre').desc(nulls_last=True),),
    'vps_asc':         (Lower('vps__nombre').asc(nulls_last=True),),
    'vps_desc':        (Lower('vps__nombre').desc(nulls_last=True),),
}


class GestionScriptsView(LoginRequiredMixin, View):
    def get(self, request):
        if not chequear_permiso(request.user, 'ver_scripts'):
            return render(request, 'software/gestion_scripts.html', {'sin_permiso': True}, status=403)

        qs = Script.objects.select_related('servicio', 'vps')
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(nombre__icontains=q) |
                Q(descripcion__icontains=q) |
                Q(servicio__nombre__icontains=q)
            )

        categoria = request.GET.get('categoria')
        if categoria:
            qs = qs.filter(categoria=categoria)

        vps_id = request.GET.get('vps')
        if vps_id:
            qs = qs.filter(vps_id=vps_id)

        orden = request.GET.get('orden') or 'nombre_asc'
        if orden not in ORDENES_SCRIPTS:
            orden = 'nombre_asc'
        qs = qs.order_by(*ORDENES_SCRIPTS[orden])

        paginator = Paginator(qs, 10)
        scripts = paginator.get_page(request.GET.get('page', 1))

        context = {
            'scripts':          scripts,
            'q':                q,
            'filtro_categoria': categoria or '',
            'filtro_vps':       vps_id or '',
            'orden':            orden,
            'categorias':       get_todas_categorias(),
            'todos_servicios':  ServicioSoftware.objects.all(),
            'todas_vps':        VPS.objects.all(),
            'puede_crear':      chequear_permiso(request.user, 'crear_scripts'),
            'puede_editar':     chequear_permiso(request.user, 'editar_scripts'),
            'puede_eliminar':   chequear_permiso(request.user, 'eliminar_scripts'),
            'sin_permiso':      False,
        }
        return render(request, 'software/gestion_scripts.html', context)


class ScriptCrearEditarAjax(LoginRequiredMixin, View):
    def post(self, request):
        pk = request.POST.get('pk')
        if pk:
            if not chequear_permiso(request.user, 'editar_scripts'):
                return JsonResponse({'error': 'Sin permiso'}, status=403)
            script = get_object_or_404(Script, pk=pk)
            form = ScriptForm(request.POST, request.FILES, instance=script)
        else:
            if not chequear_permiso(request.user, 'crear_scripts'):
                return JsonResponse({'error': 'Sin permiso'}, status=403)
            form = ScriptForm(request.POST, request.FILES)

        if form.is_valid():
            script = form.save(commit=False)
            if not pk:
                script.creado_por = request.user
            else:
                script.modificado_por = request.user
            script.save()
            return JsonResponse({'success': True, 'script': {
                'id':               script.pk,
                'nombre':           script.nombre,
                'categoria':        script.categoria,
                'servicio':         script.servicio.nombre if script.servicio else '',
                'vps':              script.vps.nombre if script.vps else '',
                'descripcion':      script.descripcion,
                'contenido':        script.contenido,
                'tiene_archivo':    bool(script.archivo),
            }})
        return JsonResponse({'success': False, 'errors': form.errors}, status=400)


class ScriptEliminarAjax(LoginRequiredMixin, View):
    def post(self, request):
        if not chequear_permiso(request.user, 'eliminar_scripts'):
            return JsonResponse({'error': 'Sin permiso'}, status=403)
        pk = request.POST.get('pk')
        script = get_object_or_404(Script, pk=pk)
        script.delete()
        return JsonResponse({'success': True})


class ScriptDescargarAjax(LoginRequiredMixin, View):
    def get(self, request, pk):
        if not chequear_permiso(request.user, 'ver_scripts'):
            return JsonResponse({'error': 'Sin permiso'}, status=403)
        script = get_object_or_404(Script, pk=pk)
        if script.archivo:
            return FileResponse(script.archivo.open('rb'), as_attachment=True,
                                 filename=script.archivo.name.split('/')[-1])
        if script.contenido:
            from django.http import HttpResponse
            nombre_archivo = f"{script.nombre.strip().replace(' ', '_')}.sh"
            response = HttpResponse(script.contenido, content_type='text/plain; charset=utf-8')
            response['Content-Disposition'] = f'attachment; filename="{nombre_archivo}"'
            return response
        raise Http404
