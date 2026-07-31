from django import forms
from .models import Servicio

class ServicioForm(forms.ModelForm):
    class Meta:
        model = Servicio
        fields = ['codigo', 'descripcion', 'monto', 'activo', 'proveedor',
                  'tipo_precio', 'rango_desde', 'rango_hasta']
        widgets = {
            'codigo': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: EX1'}),
            'descripcion': forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
            'monto': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'activo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'proveedor': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Rapipago, Pago Fácil'}),
            'tipo_precio': forms.Select(attrs={'class': 'form-control'}),
            'rango_desde': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'rango_hasta': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['codigo'].required = True
        self.fields['descripcion'].required = True
        self.fields['monto'].required = True
        self.fields['rango_desde'].required = False
        self.fields['rango_hasta'].required = False

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('tipo_precio') == Servicio.TIPO_RANGO:
            desde = cleaned.get('rango_desde')
            hasta = cleaned.get('rango_hasta')
            if desde is None or hasta is None:
                raise forms.ValidationError(
                    'Los servicios "Por rango" necesitan rango_desde y rango_hasta.'
                )
            if desde > hasta:
                raise forms.ValidationError('rango_desde no puede ser mayor que rango_hasta.')
        return cleaned