from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render
from django.views import View

from .models import VPS, ServicioSoftware, Instalacion, Script, Nota


class InicioSoftwareView(LoginRequiredMixin, View):
    def get(self, request):
        context = {
            'cant_vps':            VPS.objects.count(),
            'cant_servicios':      ServicioSoftware.objects.count(),
            'cant_instalaciones':  Instalacion.objects.count(),
            'cant_scripts':        Script.objects.count(),
            'cant_notas':          Nota.objects.count(),
        }
        return render(request, 'software/inicio_software.html', context)
