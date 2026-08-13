from django.contrib import admin
from .models import VPS, ServicioSoftware, Instalacion, Script

admin.site.register(VPS)
admin.site.register(ServicioSoftware)
admin.site.register(Instalacion)
admin.site.register(Script)
