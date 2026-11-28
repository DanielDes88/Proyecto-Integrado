from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError
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


class ServiceUpdateForm(forms.Form):
    name = forms.CharField(label="Nombre", max_length=100, required=False)
    price = forms.IntegerField(label="Precio en CLP", min_value=1, max_value=2147483647)
    revision = forms.UUIDField()
    image = forms.FileField(label="Imagen", required=False)
    remove_image = forms.BooleanField(required=False)

    def clean_name(self):
        name = self.cleaned_data["name"]
        if "name" in self.data and not name:
            raise ValidationError("Escribe el nombre del servicio.")
        return name

    def clean_image(self):
        uploaded = self.cleaned_data.get("image")
        if not uploaded:
            return None
        if uploaded.size > 5 * 1024 * 1024:
            raise ValidationError("La imagen debe pesar como máximo 5 MiB.")
        try:
            with Image.open(uploaded) as original:
                if original.format not in {"JPEG", "PNG", "WEBP"}:
                    raise ValidationError("Selecciona una imagen JPG, PNG o WebP.")
                if original.width * original.height > 16_000_000:
                    raise ValidationError("La imagen debe tener como máximo 16 megapíxeles.")
                image = ImageOps.exif_transpose(original)
                image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
                has_alpha = "A" in image.getbands() or "transparency" in image.info
                image = image.convert("RGBA" if has_alpha else "RGB")
                image.info.clear()
                output = BytesIO()
                if has_alpha:
                    image.save(output, format="PNG")
                    content_type = "image/png"
                else:
                    image.save(output, format="JPEG", quality=85)
                    content_type = "image/jpeg"
                return output.getvalue(), content_type
        except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError) as error:
            raise ValidationError("El archivo no contiene una imagen válida o está dañado.") from error

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("image") and cleaned.get("remove_image"):
            raise ValidationError("Elige una imagen nueva o marca quitar imagen.")
        return cleaned


class ServiceCreateForm(ServiceUpdateForm):
    name = forms.CharField(label="Nombre", max_length=100)
    category = forms.CharField(label="Categoría", max_length=50)
    description = forms.CharField(label="Descripción", max_length=250)
    duration = forms.IntegerField(label="Duración en minutos", min_value=1, max_value=2147483647)
    creation_key = forms.UUIDField()
    revision = None
    remove_image = None


class ServiceDeleteForm(forms.Form):
    revision = forms.UUIDField()
