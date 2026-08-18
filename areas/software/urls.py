from django.urls import path
from . import views
from . import views_vps
from . import views_servicios
from . import views_instalaciones
from . import views_scripts
from . import views_backup

app_name = 'software'

urlpatterns = [
    # ── Inicio ────────────────────────────────────────────────
    path('', views.InicioSoftwareView.as_view(), name='index'),

    # ── Backup (exportar / importar toda la DB del área) ────────
    path('backup/exportar/', views_backup.SoftwareExportarView.as_view(), name='backup_exportar'),
    path('backup/importar/', views_backup.SoftwareImportarAjax.as_view(), name='backup_importar'),

    # ── VPS ───────────────────────────────────────────────────
    path('vps/', views_vps.GestionVpsView.as_view(), name='gestion_vps'),
    path('vps/acciones/', views_vps.VpsCrearEditarAjax.as_view(), name='vps_acciones'),
    path('vps/eliminar/', views_vps.VpsEliminarAjax.as_view(), name='vps_eliminar'),

    # ── Catálogo de servicios ───────────────────────────────────
    path('servicios/', views_servicios.GestionServiciosSoftwareView.as_view(), name='gestion_servicios'),
    path('servicios/acciones/', views_servicios.ServicioSoftwareCrearEditarAjax.as_view(), name='servicio_acciones'),
    path('servicios/eliminar/', views_servicios.ServicioSoftwareEliminarAjax.as_view(), name='servicio_eliminar'),

    # ── Instalaciones ────────────────────────────────────────────
    path('instalaciones/', views_instalaciones.GestionInstalacionesView.as_view(), name='gestion_instalaciones'),
    path('instalaciones/acciones/', views_instalaciones.InstalacionCrearEditarAjax.as_view(), name='instalacion_acciones'),
    path('instalaciones/eliminar/', views_instalaciones.InstalacionEliminarAjax.as_view(), name='instalacion_eliminar'),
    path('instalaciones/<int:pk>/qr/', views_instalaciones.InstalacionQrView.as_view(), name='instalacion_qr'),

    # ── Scripts ──────────────────────────────────────────────────
    path('scripts/', views_scripts.GestionScriptsView.as_view(), name='gestion_scripts'),
    path('scripts/acciones/', views_scripts.ScriptCrearEditarAjax.as_view(), name='script_acciones'),
    path('scripts/eliminar/', views_scripts.ScriptEliminarAjax.as_view(), name='script_eliminar'),
    path('scripts/<int:pk>/descargar/', views_scripts.ScriptDescargarAjax.as_view(), name='script_descargar'),
]
