from django.urls import path
from . import views
from . import views_cobros
from . import views_caja

app_name = 'cobranzas'

urlpatterns = [
    # ── Inicio ──────────────────────────────────────────────
    path('', views.InicioCobranzasView.as_view(), name='index'),

    # ── Servicios ───────────────────────────────────────────
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
    path('cobros/eliminar/', views_cobros.EliminarCobrosAjax.as_view(), name='cobros_eliminar'),
    path('cobros/previsualizar-filtro/', views_cobros.PrevisualizarElimFiltroAjax.as_view(), name='cobros_previsualizar_filtro'),
    path('cobros/limpieza-automatica/', views_cobros.LimpiezaAutomaticaAjax.as_view(), name='cobros_limpieza_automatica'),

    # ── Caja / Turnos ────────────────────────────────────────
    path('caja/', views_caja.CajaView.as_view(), name='caja'),
    path('caja/estado/', views_caja.EstadoCajaAjax.as_view(), name='caja_estado'),
    path('caja/abrir/', views_caja.AbrirCajaAjax.as_view(), name='caja_abrir'),
    path('caja/cerrar-turno/', views_caja.CerrarTurnoAjax.as_view(), name='caja_cerrar_turno'),
    path('caja/retiro/', views_caja.RetiroCajaAjax.as_view(), name='caja_retiro'),
    path('caja/turnos/', views_caja.HistorialTurnosView.as_view(), name='historial_turnos'),

    # ── Cierre diario ────────────────────────────────────────
    path('cierre-diario/previsualizar/', views_caja.PrevisualizarCierreDiarioAjax.as_view(), name='cierre_previsualizar'),
    path('cierre-diario/ejecutar/', views_caja.EjecutarCierreDiarioAjax.as_view(), name='cierre_ejecutar'),
    path('cierre-diario/historial/', views_caja.HistorialCierresDiariosView.as_view(), name='historial_cierres'),
]
