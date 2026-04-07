from django.urls import path
from . import views

app_name = 'cobranzas'

urlpatterns = [
    path('', views.InicioCobranzasView.as_view(), name='index'),
    path('servicios/', views.GestionServiciosView.as_view(), name='gestion_servicios'),
    path('servicios/acciones/', views.ServicioCrearEditarAjax.as_view(), name='servicio_acciones'),
    path('servicios/eliminar/', views.ServicioEliminarAjax.as_view(), name='servicio_eliminar'),
    path('servicios/activar/', views.ServicioActivarAjax.as_view(), name='servicio_activar'),
]