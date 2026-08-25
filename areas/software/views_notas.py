from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.db.models import Q
from django.db.models.functions import Lower
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views import View

from core.permisos import chequear_permiso
from .forms import NotaForm
from .models import Nota

# Ordenamiento resuelto en la DB (ver nota en views_instalaciones.py).
ORDENES_NOTAS = {
    'modificacion_desc': ('-fecha_modificacion',),
    'modificacion_asc':  ('fecha_modificacion',),
    'creacion_desc':     ('-fecha_creacion',),
    'creacion_asc':      ('fecha_creacion',),
    'titulo_asc':        (Lower('titulo'),),
    'titulo_desc':       (Lower('titulo').desc(),),
}


class GestionNotasView(LoginRequiredMixin, View):
    def get(self, request):
        if not chequear_permiso(request.user, 'ver_notas'):
            return render(request, 'software/gestion_notas.html', {'sin_permiso': True}, status=403)

        qs = Nota.objects.select_related('creado_por', 'modificado_por')
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(titulo__icontains=q) | Q(contenido__icontains=q))

        orden = request.GET.get('orden') or 'modificacion_desc'
        if orden not in ORDENES_NOTAS:
            orden = 'modificacion_desc'
        qs = qs.order_by(*ORDENES_NOTAS[orden])

        paginator = Paginator(qs, 10)
        notas = paginator.get_page(request.GET.get('page', 1))

        context = {
            'notas':          notas,
            'q':              q,
            'orden':          orden,
            'puede_crear':    chequear_permiso(request.user, 'crear_notas'),
            'puede_editar':   chequear_permiso(request.user, 'editar_notas'),
            'puede_eliminar': chequear_permiso(request.user, 'eliminar_notas'),
            'sin_permiso':    False,
        }
        return render(request, 'software/gestion_notas.html', context)


class NotaCrearEditarAjax(LoginRequiredMixin, View):
    def post(self, request):
        pk = request.POST.get('pk')
        if pk:
            if not chequear_permiso(request.user, 'editar_notas'):
                return JsonResponse({'error': 'Sin permiso'}, status=403)
            nota = get_object_or_404(Nota, pk=pk)
            form = NotaForm(request.POST, instance=nota)
        else:
            if not chequear_permiso(request.user, 'crear_notas'):
                return JsonResponse({'error': 'Sin permiso'}, status=403)
            form = NotaForm(request.POST)

        if form.is_valid():
            nota = form.save(commit=False)
            if not pk:
                nota.creado_por = request.user
            else:
                nota.modificado_por = request.user
            nota.save()
            return JsonResponse({'success': True, 'nota': {
                'id':        nota.pk,
                'titulo':    nota.titulo,
                'contenido': nota.contenido,
            }})
        return JsonResponse({'success': False, 'errors': form.errors}, status=400)


class NotaEliminarAjax(LoginRequiredMixin, View):
    def post(self, request):
        if not chequear_permiso(request.user, 'eliminar_notas'):
            return JsonResponse({'error': 'Sin permiso'}, status=403)
        pk = request.POST.get('pk')
        nota = get_object_or_404(Nota, pk=pk)
        nota.delete()
        return JsonResponse({'success': True})
