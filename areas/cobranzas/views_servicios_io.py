"""
views_servicios_io.py
Import / export reutilizable del catálogo de Servicio, en CSV.

Diseñado para que una carga con errores no deje la tabla a medio
importar: se valida el archivo completo antes de escribir nada, y
todo el upsert corre dentro de una única transacción atómica.
"""
import csv
import io
from decimal import Decimal, InvalidOperation

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.views import View

from core.permisos import chequear_permiso
from .models import Servicio
from .views import familia_desde_codigo

COLUMNAS_CSV = [
    'codigo', 'descripcion', 'monto', 'activo', 'proveedor',
    'familia', 'tipo_precio', 'rango_desde', 'rango_hasta',
]


class ExportarServiciosCsvAjax(LoginRequiredMixin, View):
    def get(self, request):
        if not chequear_permiso(request.user, 'ver_servicios'):
            return JsonResponse({'error': 'Sin permiso'}, status=403)

        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="servicios.csv"'
        # BOM para que Excel abra el UTF-8 sin romper acentos
        response.write('﻿')

        writer = csv.writer(response)
        writer.writerow(COLUMNAS_CSV)
        for s in Servicio.objects.all().order_by('codigo'):
            writer.writerow([
                s.codigo, s.descripcion, s.monto, 'SI' if s.activo else 'NO',
                s.proveedor, s.familia, s.tipo_precio,
                s.rango_desde if s.rango_desde is not None else '',
                s.rango_hasta if s.rango_hasta is not None else '',
            ])
        return response


def _parse_bool(valor: str) -> bool:
    return str(valor).strip().upper() in ('SI', 'TRUE', '1', 'YES', 'X')


def _parse_decimal(valor: str, campo: str, fila_num: int, errores: list):
    valor = (valor or '').strip().replace(',', '.')
    if valor == '':
        return None
    try:
        return Decimal(valor)
    except InvalidOperation:
        errores.append(f'Fila {fila_num}: "{campo}" no es un número válido ("{valor}").')
        return None


class ImportarServiciosCsvAjax(LoginRequiredMixin, View):
    def post(self, request):
        if not chequear_permiso(request.user, 'crear_servicios'):
            return JsonResponse({'error': 'Sin permiso'}, status=403)

        archivo = request.FILES.get('archivo')
        if not archivo:
            return JsonResponse({'error': 'No se recibió ningún archivo.'}, status=400)

        try:
            texto = archivo.read().decode('utf-8-sig')
        except UnicodeDecodeError:
            return JsonResponse({'error': 'El archivo debe estar en UTF-8 (o UTF-8 con BOM).'}, status=400)

        reader = csv.DictReader(io.StringIO(texto))
        columnas_faltantes = {'codigo', 'descripcion', 'monto'} - set(
            (reader.fieldnames or [])
        )
        if columnas_faltantes:
            return JsonResponse({
                'error': f'Faltan columnas obligatorias en el CSV: {", ".join(sorted(columnas_faltantes))}.'
            }, status=400)

        errores = []
        filas_validas = []
        codigos_vistos = set()

        for i, fila in enumerate(reader, start=2):  # fila 1 = encabezado
            codigo = (fila.get('codigo') or '').strip().upper()
            descripcion = (fila.get('descripcion') or '').strip()

            if not codigo:
                errores.append(f'Fila {i}: falta el código.')
                continue
            if codigo in codigos_vistos:
                errores.append(f'Fila {i}: código "{codigo}" repetido dentro del mismo archivo.')
                continue
            codigos_vistos.add(codigo)

            if not descripcion:
                errores.append(f'Fila {i}: falta la descripción ({codigo}).')
                continue

            monto = _parse_decimal(fila.get('monto', ''), 'monto', i, errores)
            if monto is None:
                errores.append(f'Fila {i}: falta el monto ({codigo}).')
                continue

            tipo_precio = (fila.get('tipo_precio') or Servicio.TIPO_FIJO).strip().lower()
            if tipo_precio not in (Servicio.TIPO_FIJO, Servicio.TIPO_RANGO):
                errores.append(
                    f'Fila {i}: tipo_precio inválido "{tipo_precio}" ({codigo}). '
                    f'Debe ser "fijo" o "rango".'
                )
                continue

            rango_desde = _parse_decimal(fila.get('rango_desde', ''), 'rango_desde', i, errores)
            rango_hasta = _parse_decimal(fila.get('rango_hasta', ''), 'rango_hasta', i, errores)

            if tipo_precio == Servicio.TIPO_RANGO:
                if rango_desde is None or rango_hasta is None:
                    errores.append(
                        f'Fila {i}: "{codigo}" es tipo_precio=rango y necesita '
                        f'rango_desde y rango_hasta.'
                    )
                    continue
                if rango_desde > rango_hasta:
                    errores.append(
                        f'Fila {i}: "{codigo}" tiene rango_desde ({rango_desde}) '
                        f'mayor que rango_hasta ({rango_hasta}).'
                    )
                    continue

            familia = (fila.get('familia') or '').strip().upper() or familia_desde_codigo(codigo)

            filas_validas.append({
                'descripcion': descripcion,
                'monto': monto,
                'activo': _parse_bool(fila.get('activo', 'SI')),
                'proveedor': (fila.get('proveedor') or '').strip(),
                'familia': familia,
                'tipo_precio': tipo_precio,
                'rango_desde': rango_desde if tipo_precio == Servicio.TIPO_RANGO else None,
                'rango_hasta': rango_hasta if tipo_precio == Servicio.TIPO_RANGO else None,
            })

        if errores:
            return JsonResponse({
                'success': False,
                'error': f'{len(errores)} error(es) en el archivo. No se importó nada.',
                'errores': errores,
            }, status=400)

        if not filas_validas:
            return JsonResponse({'error': 'El archivo no tiene filas para importar.'}, status=400)

        creados = 0
        actualizados = 0
        with transaction.atomic():
            for datos in filas_validas:
                _, fue_creado = Servicio.objects.update_or_create(
                    codigo=datos['codigo'],
                    defaults={**datos, 'modificado_por': request.user},
                )
                if fue_creado:
                    creados += 1
                else:
                    actualizados += 1

        return JsonResponse({
            'success': True,
            'creados': creados,
            'actualizados': actualizados,
            'total': len(filas_validas),
        })
