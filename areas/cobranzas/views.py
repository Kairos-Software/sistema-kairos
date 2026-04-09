from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View
from django.core.paginator import Paginator
from django.db.models import Q, ProtectedError
import re

from core.permisos import chequear_permiso
from .models import Servicio
from .forms import ServicioForm

# ─────────────────────────────────────────────
# Prefijos almacenados en memoria (JSON-like).
# Se pueden agregar dinámicamente desde el form.
# En una instalación nueva empiezan con estos defaults.
# ─────────────────────────────────────────────
PREFIJOS_DEFAULT = ['EX', 'TR']

# Guardamos en módulo para que persista mientras corre el proceso.
# Para persistencia real entre reinicios usá caché/DB; esto es suficiente
# para la mayoría de los casos de uso.
_prefijos_extra: list[str] = []


def get_todos_prefijos() -> list[str]:
    """Devuelve prefijos default + los agregados dinámicamente, sin duplicados, ordenados."""
    todos = list(dict.fromkeys(PREFIJOS_DEFAULT + _prefijos_extra))
    return sorted(todos)


def get_siguiente_codigo(prefijo: str) -> str:
    """
    Busca el último número usado para ese prefijo en la DB
    y retorna el siguiente código. Ej: si existe EX3, retorna EX4.
    """
    prefijo_upper = prefijo.upper().strip()
    # Busca todos los códigos que empiecen con ese prefijo seguido de dígitos
    existentes = (
        Servicio.objects
        .filter(codigo__istartswith=prefijo_upper)
        .values_list('codigo', flat=True)
    )
    max_num = 0
    patron = re.compile(rf'^{re.escape(prefijo_upper)}(\d+)$', re.IGNORECASE)
    for cod in existentes:
        m = patron.match(cod)
        if m:
            max_num = max(max_num, int(m.group(1)))
    return f"{prefijo_upper}{max_num + 1}"


# ─────────────────────────────────────────────
# Vistas
# ─────────────────────────────────────────────

class InicioCobranzasView(LoginRequiredMixin, View):
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

        monto = request.GET.get('monto', '').strip()
        if monto:
            try:
                monto_f = float(monto)
                qs = qs.filter(monto=monto_f)
            except ValueError:
                pass

        activo = request.GET.get('activo')
        if activo in ('true', 'false'):
            qs = qs.filter(activo=(activo == 'true'))

        # NOTA: el ordenamiento se dejó intencionalmente al cliente (JS).
        # Esto evita inconsistencias entre motores de base de datos (SQLite vs
        # PostgreSQL) y collations distintas en producción.
        # El JS en gestion_servicios.js se encarga de ordenar la tabla.
        # Solo aplicamos un orden base neutral por PK para que la paginación
        # sea estable y no varíe entre páginas.
        qs = qs.order_by('pk')

        paginator = Paginator(qs, 8)
        servicios = paginator.get_page(request.GET.get('page', 1))

        context = {
            'servicios': servicios,
            'q': q,
            'filtro_activo': activo,
            'puede_crear': chequear_permiso(request.user, 'crear_servicios'),
            'puede_editar': chequear_permiso(request.user, 'editar_servicios'),
            'puede_eliminar': chequear_permiso(request.user, 'eliminar_servicios'),
            'sin_permiso': False,
            'prefijos': get_todos_prefijos(),
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
        try:
            servicio.delete()
            return JsonResponse({'success': True})
        except ProtectedError:
            return JsonResponse({
                'success': False,
                'error': (
                    f'No se puede eliminar "{servicio.codigo}" porque tiene cobros registrados. '
                    f'Podés desactivarlo en su lugar para que no aparezca en nuevos cobros.'
                )
            }, status=400)


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


class ServicioSiguienteCodigoAjax(LoginRequiredMixin, View):
    """Devuelve el siguiente código disponible para un prefijo dado."""
    def get(self, request):
        prefijo = request.GET.get('prefijo', '').strip().upper()
        if not prefijo:
            return JsonResponse({'error': 'Prefijo requerido'}, status=400)
        siguiente = get_siguiente_codigo(prefijo)
        return JsonResponse({'codigo': siguiente})


class PrefijosAjax(LoginRequiredMixin, View):
    """GET → lista de prefijos. POST → agrega un prefijo nuevo."""
    def get(self, request):
        return JsonResponse({'prefijos': get_todos_prefijos()})

    def post(self, request):
        if not chequear_permiso(request.user, 'crear_servicios'):
            return JsonResponse({'error': 'Sin permiso'}, status=403)

        accion = request.POST.get('accion', 'agregar')

        if accion == 'eliminar':
            prefijo = request.POST.get('prefijo', '').strip().upper()
            if not prefijo:
                return JsonResponse({'error': 'Prefijo vacío'}, status=400)
            if prefijo in PREFIJOS_DEFAULT:
                return JsonResponse({'error': f'El prefijo {prefijo} es predeterminado y no se puede eliminar.'}, status=400)
            if prefijo in _prefijos_extra:
                _prefijos_extra.remove(prefijo)
            return JsonResponse({'prefijos': get_todos_prefijos()})

        # accion == 'agregar' (default)
        nuevo = request.POST.get('prefijo', '').strip().upper()
        if not nuevo:
            return JsonResponse({'error': 'Prefijo vacío'}, status=400)
        if not re.match(r'^[A-Z]{1,10}$', nuevo):
            return JsonResponse({'error': 'El prefijo solo puede contener letras (máx. 10)'}, status=400)
        if nuevo not in _prefijos_extra and nuevo not in PREFIJOS_DEFAULT:
            _prefijos_extra.append(nuevo)
        return JsonResponse({'prefijos': get_todos_prefijos()})