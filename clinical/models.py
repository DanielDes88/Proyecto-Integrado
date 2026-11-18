import uuid
from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q

class Service(models.Model):
    name = models.CharField("nombre", max_length=100)
    category = models.CharField("categoría", max_length=50)
    icon = models.CharField(max_length=5, default="✚")
    price = models.PositiveIntegerField("precio CLP")
    duration = models.PositiveIntegerField("duración en minutos", default=30)
    code = models.CharField("código", max_length=20, unique=True)
    description = models.CharField("descripción", max_length=250)
    class Meta:
        ordering = ["id"]
        verbose_name = "servicio"
        constraints = [models.CheckConstraint(condition=Q(duration__gt=0), name="service_duration_positive")]
    def __str__(self): return self.name

class DemoWorkspace(models.Model):
    """Cada sesión de navegador recibe su propia demostración aislada."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    bill_sent = models.BooleanField(default=False)
    def __str__(self): return str(self.id)

class Appointment(models.Model):
    STATUS = [(x,x) for x in ["Confirmada","En camino","En atención","Finalizada","Cancelada"]]
    workspace = models.ForeignKey(DemoWorkspace, on_delete=models.CASCADE)
    patient = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name='patient_appointments')
    professional = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name='professional_appointments')
    service = models.ForeignKey(Service, on_delete=models.PROTECT)
    date = models.DateField("fecha")
    time = models.TimeField("hora")
    address = models.CharField("dirección ficticia", max_length=80)
    destination_latitude = models.FloatField("Latitud de destino", null=True, blank=True, validators=[MinValueValidator(-90), MaxValueValidator(90)])
    destination_longitude = models.FloatField("Longitud de destino", null=True, blank=True, validators=[MinValueValidator(-180), MaxValueValidator(180)])
    status = models.CharField("estado", max_length=20, choices=STATUS, default="Confirmada")
    price = models.PositiveIntegerField("precio histórico CLP")
    duration = models.PositiveIntegerField("duración histórica en minutos")
    payment_key = models.UUIDField(default=uuid.uuid4)
    paid = models.BooleanField("pago confirmado", default=False)
    payment_status = models.CharField(
        "estado del pago",
        max_length=12,
        choices=[(x, x) for x in ["pending", "paid", "rejected", "cancelled"]],
        default="pending",
    )
    flow_order = models.CharField(max_length=30, blank=True, default="")
    flow_token = models.CharField(max_length=100, blank=True, null=True, unique=True)
    flow_url = models.URLField(max_length=500, blank=True, default="")
    conditions_accepted = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ["-created_at"]
        verbose_name = "atención de demostración"
        constraints = [
            models.UniqueConstraint(fields=["workspace", "payment_key"], name="demo_payment_idempotent"),
            models.UniqueConstraint(fields=["workspace", "date", "time"], condition=~Q(status="Cancelada"), name="demo_unique_active_slot"),
            models.CheckConstraint(condition=Q(status__in=["Confirmada","En camino","En atención","Finalizada","Cancelada"]), name="appointment_valid_status"),
        ]
    @property
    def code(self): return f"GC-{self.pk:04d}"
    def __str__(self): return self.code

class Applicant(models.Model):
    workspace = models.ForeignKey(DemoWorkspace, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    area = models.CharField(max_length=50)
    experience = models.CharField(max_length=30)
    status = models.CharField(max_length=20, choices=[(x,x) for x in ["Pendiente","Aprobado","Rechazado"]], default="Pendiente")
    def __str__(self): return self.name

class Review(models.Model):
    appointment = models.OneToOneField(Appointment, on_delete=models.CASCADE)
    rating = models.PositiveSmallIntegerField()
    comment = models.CharField(max_length=300)
    status = models.CharField(max_length=20, choices=[("Pendiente","Pendiente"),("Aprobado","Aprobado")], default="Pendiente")
    class Meta:
        constraints = [models.CheckConstraint(condition=Q(rating__gte=1, rating__lte=5), name="review_rating_range")]

class Availability(models.Model):
    professional = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name='availability')
    workspace = models.ForeignKey(DemoWorkspace, on_delete=models.CASCADE)
    weekday = models.CharField(max_length=12)
    start = models.TimeField()
    end = models.TimeField()
    class Meta:
        ordering = ["id"]
        constraints = [models.CheckConstraint(condition=Q(end__gt=models.F("start")), name="availability_valid_range"), models.UniqueConstraint(fields=["workspace","weekday","start","end"], name="availability_unique")]

class UserProfile(models.Model):
    ROLES = [('paciente','Paciente'),('profesional','Profesional'),('admin','Administrador')]
    user = models.OneToOneField(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name='clinical_profile')
    role = models.CharField(max_length=20,choices=ROLES)
    workspace = models.ForeignKey(DemoWorkspace,on_delete=models.PROTECT)
    bill_sent = models.BooleanField(default=False)
    def __str__(self): return f'{self.user.username} — {self.get_role_display()}'

class ClinicalDocument(models.Model):
    CATEGORIES = [(x, x) for x in ["Receta médica", "Orden médica", "Diagnóstico", "Examen", "Otro"]]
    patient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="clinical_documents")
    appointment = models.ForeignKey(Appointment, on_delete=models.PROTECT, related_name="documents")
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="uploaded_clinical_documents")
    category = models.CharField(max_length=30, choices=CATEGORIES)
    original_name = models.CharField(max_length=120)
    content_type = models.CharField(max_length=40)
    size = models.PositiveIntegerField()
    mongo_id = models.CharField(max_length=24, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self): return f"{self.category} · {self.patient_id}"


class TripLocation(models.Model):
    """Guarda la última posición de una visita activa."""

    appointment = models.OneToOneField(Appointment, on_delete=models.CASCADE, primary_key=True)
    share_id = models.UUIDField()
    latitude = models.FloatField()
    longitude = models.FloatField()
    received_at = models.DateTimeField()
    route_requested_at = models.DateTimeField(null=True)
