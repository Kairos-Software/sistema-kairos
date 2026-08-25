from django import forms
from .models import VPS, ServicioSoftware, Instalacion, Script, Nota


class VPSForm(forms.ModelForm):
    class Meta:
        model  = VPS
        fields = [
            'nombre', 'proveedor', 'ip', 'plan', 'fecha_vencimiento',
            'nucleos_cpu', 'memoria', 'espacio_disco', 'ancho_banda', 'sistema_operativo',
            'usuario_ssh', 'acceso_ssh', 'notas', 'activa',
        ]
        widgets = {
            'nombre':            forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: VPS Clientes 1'}),
            'proveedor':         forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Hostinger'}),
            'ip':                forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: 85.120.32.5'}),
            'plan':              forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: KVM 1'}),
            'fecha_vencimiento': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'nucleos_cpu':       forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Ej: 1'}),
            'memoria':           forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: 4 GB'}),
            'espacio_disco':     forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: 50 GB'}),
            'ancho_banda':       forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: 4 TB'}),
            'sistema_operativo': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Ubuntu 24.04 LTS'}),
            'usuario_ssh':       forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'root'}),
            'acceso_ssh':        forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: ssh root@85.209.92.238'}),
            'notas':             forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
            'activa':            forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class ServicioSoftwareForm(forms.ModelForm):
    class Meta:
        model  = ServicioSoftware
        fields = ['nombre', 'descripcion', 'activo']
        widgets = {
            'nombre':      forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Kai-Cart'}),
            'descripcion': forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
            'activo':      forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class InstalacionForm(forms.ModelForm):
    class Meta:
        model  = Instalacion
        fields = [
            'vps', 'servicio', 'cliente', 'cliente_texto', 'dominio', 'puerto',
            'ruta_proyecto', 'ruta_service', 'ruta_conf', 'estado', 'descripcion', 'comandos',
            'usuario_admin', 'contrasena_admin',
        ]
        widgets = {
            'vps':            forms.Select(attrs={'class': 'form-control'}),
            'servicio':       forms.Select(attrs={'class': 'form-control'}),
            'cliente':        forms.HiddenInput(),
            'cliente_texto':  forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Cliente sin cargar en el sistema'}),
            'dominio':        forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: cliente.miapp.com'}),
            'puerto':         forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Ej: 8000'}),
            'ruta_proyecto':  forms.TextInput(attrs={'class': 'form-control', 'placeholder': '/home/deploy/proyecto'}),
            'ruta_service':   forms.TextInput(attrs={'class': 'form-control', 'placeholder': '/etc/systemd/system/proyecto.service'}),
            'ruta_conf':      forms.TextInput(attrs={'class': 'form-control', 'placeholder': '/etc/nginx/sites-available/proyecto.conf'}),
            'estado':         forms.Select(attrs={'class': 'form-control'}),
            'descripcion':    forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
            'comandos':       forms.Textarea(attrs={'rows': 6, 'class': 'form-control code-textarea', 'spellcheck': 'false',
                                                      'placeholder': 'cd /home/deploy/proyecto && git pull && systemctl restart proyecto'}),
            'usuario_admin':    forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: admin', 'autocomplete': 'off'}),
            'contrasena_admin': forms.TextInput(attrs={'class': 'form-control', 'type': 'password', 'autocomplete': 'off'}),
        }

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('cliente') and cleaned.get('cliente_texto'):
            cleaned['cliente_texto'] = ''
        return cleaned


class ScriptForm(forms.ModelForm):
    class Meta:
        model  = Script
        fields = ['nombre', 'categoria', 'servicio', 'vps', 'descripcion', 'contenido', 'archivo']
        widgets = {
            'nombre':      forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Abrir puertos 9000 y 5432'}),
            # El campo visible es un <select> + input "nueva categoría" manejados por JS;
            # este input hidden es el que realmente viaja en el POST.
            'categoria':   forms.HiddenInput(),
            'servicio':    forms.Select(attrs={'class': 'form-control'}),
            'vps':         forms.Select(attrs={'class': 'form-control'}),
            'descripcion': forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
            'contenido':   forms.Textarea(attrs={'rows': 12, 'class': 'form-control code-textarea', 'spellcheck': 'false'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['servicio'].required = False
        self.fields['servicio'].empty_label = '— Sin asociar —'
        self.fields['vps'].required = False
        self.fields['vps'].empty_label = '— Todas / cualquiera —'

    def clean(self):
        cleaned = super().clean()
        contenido = cleaned.get('contenido')
        archivo   = cleaned.get('archivo') or getattr(self.instance, 'archivo', None)
        if not contenido and not archivo:
            raise forms.ValidationError('Cargá el contenido del script o subí un archivo.')
        return cleaned


class NotaForm(forms.ModelForm):
    class Meta:
        model  = Nota
        fields = ['titulo', 'contenido']
        widgets = {
            'titulo':    forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Tareas Kai-Cart'}),
            'contenido': forms.Textarea(attrs={'rows': 14, 'class': 'form-control',
                                                'placeholder': 'Correcciones pendientes, apuntes, tareas...'}),
        }
