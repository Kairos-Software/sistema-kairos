from django.urls import path
from . import views
from . import views_cobros

app_name = 'cobranzas'

urlpatterns = [
    # ── Servicios ───────────────────────────────────────────
    path('', views.InicioCobranzasView.as_view(), name='index'),
    path('servicios/', views.GestionServiciosView.as_view(), name='gestion_servicios'),
    path('servicios/acciones/', views.ServicioCrearEditarAjax.as_view(), name='servicio_acciones'),
    path('servicios/eliminar/', views.ServicioEliminarAjax.as_view(), name='servicio_eliminar'),
    path('servicios/activar/', views.ServicioActivarAjax.as_view(), name='servicio_activar'),
    path('servicios/siguiente-codigo/', views.ServicioSiguienteCodigoAjax.as_view(), name='servicio_siguiente_codigo'),
    path('servicios/prefijos/', views.PrefijosAjax.as_view(), name='servicio_prefijos'),

    # ── Cobros ──────────────────────────────────────────────
    path('cobros/', views_cobros.GestionCobrosView.as_view(), name='gestion_cobros'),
    path('cobros/buscar-servicio/', views_cobros.BuscarServicioAjax.as_view(), name='cobro_buscar_servicio'),
    path('cobros/confirmar/', views_cobros.ConfirmarCobroAjax.as_view(), name='cobro_confirmar'),
    path('cobros/historial/', views_cobros.HistorialCobrosView.as_view(), name='historial_cobros'),

    # ── Gestión / eliminación de cobros ─────────────────────
    path('cobros/eliminar/', views_cobros.EliminarCobrosAjax.as_view(), name='cobros_eliminar'),
    path('cobros/previsualizar-filtro/', views_cobros.PrevisualizarElimFiltroAjax.as_view(), name='cobros_previsualizar_filtro'),
    path('cobros/limpieza-automatica/', views_cobros.LimpiezaAutomaticaAjax.as_view(), name='cobros_limpieza_automatica'),
]