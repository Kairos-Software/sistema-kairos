"""
cargar_conceptos_iniciales.py

Carga única de los conceptos/servicios reales desde la hoja BASE_CONCEPTOS
del Excel de referencia (Sistema_Control_Caja_Diaria.xlsm), reemplazando
los servicios de prueba (EX1/EX2/EX3) que había en la base.

No depende de openpyxl: lee el .xlsm directamente como zip+XML (todo
stdlib), porque el venv del proyecto no tiene esa librería instalada.

Uso:
    python manage.py cargar_conceptos_iniciales
    python manage.py cargar_conceptos_iniciales --file "D:\\ruta\\a\\otro.xlsm"

Es idempotente: upsert por código, correrlo dos veces no duplica nada.
"""
import re
import zipfile
import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import ProtectedError

from areas.cobranzas.models import Servicio
from areas.cobranzas.views import familia_desde_codigo

NS = {'main': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}

DEFAULT_PATH = r'D:\Desktop\Sistema_Control_Caja_Diaria.xlsm'
HOJA_OBJETIVO = 'BASE_CONCEPTOS'

# ── Patrones de rango dentro del texto del CONCEPTO ────────────────────────
# Se prueban en orden; el primero que matchea gana.
_PATRON_DESDE_HASTA_ABIERTO = re.compile(
    r'desde\s*\$?\s*([\d.,]+)\s*/\s*en\s*adelante', re.IGNORECASE)
_PATRON_DESDE_HASTA = re.compile(
    r'desde\s*\$?\s*([\d.,]+)\s*/\s*hasta\s*\$?\s*([\d.,]+)', re.IGNORECASE)
_PATRON_DE_A_ABIERTO = re.compile(
    r'\bde\s*\$?\s*([\d.,]+)\s*en\s*adelante', re.IGNORECASE)
_PATRON_DE_A = re.compile(
    r'\bde\s*\$?\s*([\d.,]+)\s*a\s*\$?\s*([\d.,]+)', re.IGNORECASE)

SIN_TOPE = Decimal('999999999.99')


def parse_monto_ar(texto: str) -> Decimal:
    """'2.000.001' -> 2000001 ; '1.234,56' -> 1234.56 (formato AR)."""
    limpio = texto.strip().replace('.', '').replace(',', '.')
    return Decimal(limpio)


def extraer_rango(concepto: str):
    """
    Devuelve (desde, hasta) si encuentra un patrón de rango confiable,
    o None si el texto no tiene uno (servicio de precio fijo) o el
    patrón encontrado es ambiguo/inconsistente (desde > hasta).
    """
    m = _PATRON_DESDE_HASTA_ABIERTO.search(concepto)
    if m:
        try:
            return (parse_monto_ar(m.group(1)), SIN_TOPE)
        except InvalidOperation:
            return None

    m = _PATRON_DESDE_HASTA.search(concepto)
    if m:
        try:
            desde, hasta = parse_monto_ar(m.group(1)), parse_monto_ar(m.group(2))
        except InvalidOperation:
            return None
        return (desde, hasta) if desde <= hasta else None

    m = _PATRON_DE_A_ABIERTO.search(concepto)
    if m:
        try:
            return (parse_monto_ar(m.group(1)), SIN_TOPE)
        except InvalidOperation:
            return None

    m = _PATRON_DE_A.search(concepto)
    if m:
        try:
            desde, hasta = parse_monto_ar(m.group(1)), parse_monto_ar(m.group(2))
        except InvalidOperation:
            return None
        return (desde, hasta) if desde <= hasta else None

    return None


def leer_base_conceptos(ruta_xlsm: str, hoja: str = HOJA_OBJETIVO):
    """
    Lee una hoja de un .xlsm (zip+XML, sin dependencias externas) y
    devuelve una lista de filas [(codigo, concepto, importe, activo), ...],
    saltando el encabezado.
    """
    try:
        z = zipfile.ZipFile(ruta_xlsm)
    except FileNotFoundError:
        raise CommandError(f'No se encontró el archivo: {ruta_xlsm}')
    except zipfile.BadZipFile:
        raise CommandError(f'"{ruta_xlsm}" no es un .xlsx/.xlsm válido.')

    shared = []
    if 'xl/sharedStrings.xml' in z.namelist():
        root = ET.fromstring(z.read('xl/sharedStrings.xml'))
        for si in root.findall('main:si', NS):
            textos = si.findall('.//main:t', NS)
            shared.append(''.join(t.text or '' for t in textos))

    wb_root = ET.fromstring(z.read('xl/workbook.xml'))
    hojas = {}
    for sheet in wb_root.findall('.//main:sheets/main:sheet', NS):
        rid = sheet.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
        hojas[sheet.get('name')] = rid

    if hoja not in hojas:
        raise CommandError(
            f'La hoja "{hoja}" no existe en el archivo. Hojas disponibles: {", ".join(hojas)}'
        )

    rels_root = ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
    rid_a_target = {
        rel.get('Id'): rel.get('Target')
        for rel in rels_root.findall(
            '{http://schemas.openxmlformats.org/package/2006/relationships}Relationship'
        )
    }
    target = rid_a_target[hojas[hoja]]
    sheet_path = target if target.startswith('xl/') else f'xl/{target}'

    def valor_celda(c):
        t = c.get('t')
        is_el = c.find('main:is', NS)
        if is_el is not None:
            return ''.join(t.text or '' for t in is_el.findall('.//main:t', NS))
        v_el = c.find('main:v', NS)
        if v_el is None:
            return ''
        val = v_el.text or ''
        if t == 's':
            try:
                return shared[int(val)]
            except (ValueError, IndexError):
                return ''
        return val

    sheet_root = ET.fromstring(z.read(sheet_path))
    filas = []
    for row in sheet_root.findall('.//main:sheetData/main:row', NS):
        por_col = {}
        for c in row.findall('main:c', NS):
            col_letra = re.match(r'^[A-Z]+', c.get('r')).group(0)
            por_col[col_letra] = valor_celda(c)
        codigo = (por_col.get('A') or '').strip()
        if not codigo or codigo.upper() == 'CODIGO':
            continue
        filas.append((
            codigo,
            (por_col.get('B') or '').strip(),
            (por_col.get('C') or '').strip(),
            (por_col.get('D') or '').strip(),
        ))
    return filas


class Command(BaseCommand):
    help = 'Carga los conceptos/servicios reales desde BASE_CONCEPTOS del Excel de referencia.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file', dest='file', default=DEFAULT_PATH,
            help=f'Ruta al .xlsm (default: {DEFAULT_PATH})',
        )

    def handle(self, *args, **options):
        ruta = options['file']
        filas = leer_base_conceptos(ruta)
        self.stdout.write(f'Leídas {len(filas)} filas de "{HOJA_OBJETIVO}" en {ruta}')

        pruebas = Servicio.objects.filter(codigo__in=['EX1', 'EX2', 'EX3'])
        try:
            borrados, _ = pruebas.delete()
            if borrados:
                self.stdout.write(self.style.WARNING(
                    f'Borrados {borrados} servicio(s) de prueba (EX1/EX2/EX3).'
                ))
        except ProtectedError:
            actualizados_prueba = pruebas.update(activo=False)
            if actualizados_prueba:
                self.stdout.write(self.style.WARNING(
                    f'{actualizados_prueba} servicio(s) de prueba (EX1/EX2/EX3) tienen '
                    f'cobros de prueba asociados y no se pueden borrar sin borrar esos '
                    f'cobros también — se desactivaron en su lugar.'
                ))

        creados = actualizados = con_advertencia = 0

        with transaction.atomic():
            for codigo, concepto, importe_str, activo_str in filas:
                try:
                    importe = parse_monto_ar(importe_str) if importe_str else Decimal('0')
                except InvalidOperation:
                    self.stdout.write(self.style.WARNING(
                        f'{codigo}: importe inválido "{importe_str}", se usa 0.'
                    ))
                    importe = Decimal('0')
                    con_advertencia += 1

                rango = extraer_rango(concepto)
                if rango is not None:
                    tipo_precio = Servicio.TIPO_RANGO
                    rango_desde, rango_hasta = rango
                else:
                    tipo_precio = Servicio.TIPO_FIJO
                    rango_desde = rango_hasta = None
                    # Log solo si el texto parece tener un rango pero no se pudo
                    # interpretar con confianza (ej: rango invertido/typo de origen).
                    if re.search(r'\$\s*[\d.,]+', concepto) and re.search(
                        r'\b(desde|hasta|\ba\b|adelante)\b', concepto, re.IGNORECASE
                    ):
                        self.stdout.write(self.style.WARNING(
                            f'{codigo}: no se pudo interpretar el rango de forma confiable '
                            f'en "{concepto}" — se cargó como tipo_precio=fijo. Revisar a mano.'
                        ))
                        con_advertencia += 1

                _, fue_creado = Servicio.objects.update_or_create(
                    codigo=codigo.upper(),
                    defaults={
                        'descripcion': concepto,
                        'monto': importe,
                        'activo': activo_str.strip().upper() != 'NO',
                        'familia': familia_desde_codigo(codigo),
                        'tipo_precio': tipo_precio,
                        'rango_desde': rango_desde,
                        'rango_hasta': rango_hasta,
                    },
                )
                if fue_creado:
                    creados += 1
                else:
                    actualizados += 1

        self.stdout.write(self.style.SUCCESS(
            f'Listo: {creados} creado(s), {actualizados} actualizado(s), '
            f'{con_advertencia} con advertencia (revisar arriba).'
        ))
