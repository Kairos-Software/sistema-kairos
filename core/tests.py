import os
import shutil
import subprocess
import tempfile
import unittest

from django.test import TestCase
from django.urls import reverse

from .models import Usuario
from .views_respaldo import _pg_dump


class CopiaSeguridadTests(TestCase):
    """Descarga de la base completa: solo superusuarios y con la contraseña."""

    def setUp(self):
        self.url = reverse('core:copia_seguridad')
        self.admin = Usuario.objects.create_superuser('admin_resp', 'r@test.local', 'clave-correcta')

    def test_un_usuario_comun_no_puede(self):
        comun = Usuario.objects.create_user('comun_resp', 'c@test.local', 'x', is_staff=True)
        self.client.force_login(comun)
        self.assertRedirects(self.client.get(self.url), reverse('core:home'), fetch_redirect_response=False)
        r = self.client.post(self.url, {'password': 'x'})
        self.assertEqual(r.status_code, 302)
        self.assertNotIn('Content-Disposition', r)

    def test_sin_sesion_va_al_login(self):
        r = self.client.post(self.url, {'password': 'clave-correcta'})
        self.assertEqual(r.status_code, 302)
        self.assertNotIn('Content-Disposition', r)

    def test_contrasena_incorrecta_no_descarga(self):
        self.client.force_login(self.admin)
        r = self.client.post(self.url, {'password': 'otra'})
        self.assertEqual(r.status_code, 400)
        self.assertNotIn('Content-Disposition', r)
        self.assertContains(r, 'La contraseña no es correcta', status_code=400)

    def test_get_no_descarga_nada(self):
        self.client.force_login(self.admin)
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertNotIn('Content-Disposition', r)

    @unittest.skipUnless(_pg_dump(), 'pg_dump no está instalado (en Windows: PG_DUMP_PATH)')
    def test_descarga_real_que_se_puede_restaurar(self):
        temporales = lambda: {f for f in os.listdir(tempfile.gettempdir())   # noqa: E731
                              if f.startswith('kairos_') and f.endswith('.dump')}
        antes = temporales()
        self.client.force_login(self.admin)
        r = self.client.post(self.url, {'password': 'clave-correcta'})
        self.assertEqual(r.status_code, 200)
        self.assertIn('attachment; filename="kairos_', r['Content-Disposition'])
        self.assertEqual(r['Cache-Control'], 'no-store')
        contenido = b''.join(r.streaming_content)   # al terminar de leerla se cierra
        self.assertEqual(temporales(), antes)         # y el archivo temporal se borró
        self.assertTrue(contenido.startswith(b'PGDMP'))   # formato custom de pg_dump
        # pg_restore la puede leer y trae la tabla de usuarios.
        pg_restore = os.path.join(os.path.dirname(_pg_dump()), 'pg_restore') if os.path.dirname(_pg_dump()) \
            else shutil.which('pg_restore')
        ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_test_respaldo.dump')
        try:
            with open(ruta, 'wb') as f:
                f.write(contenido)
            lista = subprocess.run([pg_restore, '--list', ruta], capture_output=True, text=True, check=True).stdout
            self.assertIn('core_usuario', lista)
        finally:
            os.unlink(ruta)
