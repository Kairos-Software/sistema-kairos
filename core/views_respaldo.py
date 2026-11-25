# core/views_respaldo.py
#
# "Copia de seguridad": descarga la base de datos completa (solo superusuarios).
#
# Genera un pg_dump en formato "custom" (-Fc), el mismo que se carga con
# pg_restore. El archivo tiene TODOS los datos (clientes, cobros, usuarios con
# sus contraseñas cifradas), por eso:
#   - solo superusuarios;
#   - solo por POST con CSRF: un link o una precarga del navegador no la dispara;
#   - hay que volver a escribir la contraseña (por si quedó una sesión abierta);
#   - queda en el log del servidor quién la descargó y cuándo.
# No incluye los archivos subidos (fotos, documentos, tickets): esos están en
# la carpeta media/, no en la base.
import io
import logging
import os
import shutil
import subprocess
import tempfile

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import connection
from django.http import FileResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views import View

logger = logging.getLogger(__name__)

TIMEOUT_SEGUNDOS = 300


def _pg_dump():
    """Ruta a pg_dump: la variable de entorno PG_DUMP_PATH, o el que esté en el PATH."""
    return os.environ.get('PG_DUMP_PATH') or shutil.which('pg_dump')


class _ArchivoTemporal(io.FileIO):
    """Archivo que se borra solo cuando Django termina de enviarlo."""

    def close(self):
        try:
            super().close()
        finally:
            try:
                os.unlink(self.name)
            except OSError:
                pass


def _pantalla(request, error=None, status=200):
    return render(request, 'core/copia_seguridad.html', {
        'disponible': bool(_pg_dump()),
        'error':      error,
    }, status=status)


class CopiaSeguridadView(LoginRequiredMixin, View):
    def get(self, request):
        if not request.user.is_superuser:
            return redirect('core:home')
        return _pantalla(request)

    def post(self, request):
        if not request.user.is_superuser:
            return redirect('core:home')
        if not request.user.check_password(request.POST.get('password', '')):
            logger.warning('Copia de seguridad: contraseña incorrecta para %s', request.user.username)
            return _pantalla(request, 'La contraseña no es correcta.', status=400)

        ejecutable = _pg_dump()
        if not ejecutable:
            return _pantalla(request, 'Este servidor no tiene pg_dump instalado.', status=500)

        db = connection.settings_dict
        fd, ruta = tempfile.mkstemp(prefix='kairos_', suffix='.dump')
        os.close(fd)
        cmd = [ejecutable, '-Fc',
               '-h', db.get('HOST') or 'localhost', '-p', str(db.get('PORT') or 5432),
               '-U', db['USER'], '-d', db['NAME'], '-f', ruta]
        # La contraseña va por variable de entorno, nunca en la línea de comando.
        env = {**os.environ, 'PGPASSWORD': db.get('PASSWORD') or ''}
        try:
            r = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=TIMEOUT_SEGUNDOS)
            ok = r.returncode == 0
            detalle = r.stderr.strip()
        except (subprocess.TimeoutExpired, OSError) as e:
            ok, detalle = False, str(e)
        if not ok:
            try:
                os.unlink(ruta)
            except OSError:
                pass
            logger.error('Copia de seguridad: pg_dump falló: %s', detalle[:2000])
            return _pantalla(request, 'No se pudo generar la copia. El detalle quedó en el log del servidor.',
                             status=500)

        nombre = f'kairos_{timezone.localtime():%Y-%m-%d_%H%M}.dump'
        logger.warning('Copia de seguridad descargada por %s (%s, %s bytes)',
                       request.user.username, nombre, os.path.getsize(ruta))
        resp = FileResponse(_ArchivoTemporal(ruta, 'rb'), as_attachment=True, filename=nombre,
                            content_type='application/octet-stream')
        resp['Cache-Control'] = 'no-store'
        return resp
