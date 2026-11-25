from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import ValidationError
from django.utils import timezone


class PatientRegistrationForm(UserCreationForm):
    first_name = forms.CharField(max_length=150, label="Nombre")
    last_name = forms.CharField(max_length=150, label="Apellido")
    email = forms.EmailField(label="Correo electrónico")
    date_of_birth = forms.DateField(
        label="Fecha de nacimiento",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    phone = forms.CharField(max_length=30, label="Teléfono")
    address = forms.CharField(max_length=250, label="Dirección")
    city = forms.CharField(max_length=100, label="Comuna o ciudad")

    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ("username", "first_name", "last_name", "email")
        widgets = {
            "username": forms.TextInput(attrs={"autocomplete": "username"}),
            "first_name": forms.TextInput(attrs={"autocomplete": "given-name"}),
            "last_name": forms.TextInput(attrs={"autocomplete": "family-name"}),
            "email": forms.EmailInput(attrs={"autocomplete": "email"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Nombre de usuario"
        self.fields["username"].help_text = "Lo usarás para iniciar sesión."
        self.fields["password1"].label = "Contraseña"
        self.fields["password1"].widget.attrs["autocomplete"] = "new-password"
        self.fields["password2"].label = "Confirmar contraseña"
        self.fields["password2"].widget.attrs["autocomplete"] = "new-password"

    def clean_username(self):
        username = super().clean_username().strip().lower()
        if get_user_model().objects.filter(username__iexact=username).exists():
            raise ValidationError("Ese nombre de usuario ya está en uso.")
        return username

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if get_user_model().objects.filter(email__iexact=email).exists():
            raise ValidationError("Ya existe una cuenta con ese correo electrónico.")
        return email

    def clean_date_of_birth(self):
        date_of_birth = self.cleaned_data["date_of_birth"]
        if date_of_birth > timezone.localdate():
            raise ValidationError("La fecha de nacimiento no puede ser futura.")
        return date_of_birth
