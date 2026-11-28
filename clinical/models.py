import uuid
from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.urls import reverse


class Service(models.Model):
    name = models.CharField("nombre", max_length=100)
    category = models.CharField("categoría", max_length=50)
    icon = models.CharField(max_length=5, default="✚")
    price = models.PositiveIntegerField("precio CLP")
    duration = models.PositiveIntegerField("duración en minutos", default=30)
    code = models.CharField("código", max_length=20, unique=True)
    description = models.CharField("descripción", max_length=250)
    image_data = models.BinaryField(default=bytes, blank=True, editable=False)
    image_content_type = models.CharField(max_length=30, blank=True, default="", editable=False)
    revision = models.UUIDField(default=uuid.uuid4, editable=False)
    is_active = models.BooleanField("disponible en el catálogo", default=True)
    creation_key = models.UUIDField(null=True, blank=True, unique=True, editable=False)
    class Meta:
        ordering = ["id"]
        verbose_name = "servicio"
        constraints = [models.CheckConstraint(condition=Q(duration__gt=0), name="service_duration_positive")]
    @property
    def image_url(self):
        if not self.image_content_type:
            return ""
        return reverse("service_image", args=[self.pk, self.revision])

    def save(self, *args, **kwargs):
        self.revision = uuid.uuid4()
        if kwargs.get("update_fields") is not None:
            kwargs["update_fields"] = set(kwargs["update_fields"]) | {"revision"}
        super().save(*args, **kwargs)

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
    patient_notice = models.TextField(blank=True, default="")
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
class Transaction(models.Model):
    STATUS = [("pending", "Pendiente"), ("paid", "Aprobado"), ("rejected", "Rechazado"), ("cancelled", "Cancelado")]
    appointment = models.ForeignKey(Appointment, on_delete=models.PROTECT, related_name="transactions")
    flow_order = models.CharField(max_length=30, blank=True, default="")
    flow_token = models.CharField(max_length=100, null=True, blank=True, unique=True)
    amount = models.PositiveIntegerField("monto CLP")
    status = models.CharField(max_length=12, choices=STATUS, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        verbose_name = "transacción"    
class Applicant(models.Model):
    workspace = models.ForeignKey(DemoWorkspace, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="professional_applications")
    name = models.CharField(max_length=100)
    area = models.CharField(max_length=50)
    experience = models.CharField(max_length=30)
    has_vehicle = models.BooleanField("dispone de vehículo propio", default=False)
    status = models.CharField(max_length=20, choices=[(x,x) for x in ["Pendiente","Aprobado","Rechazado"]], default="Pendiente")
    submitted_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="reviewed_applications")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(blank=True, default="")
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "workspace"],
                condition=Q(user__isnull=False, status="Pendiente"),
                name="applicant_one_pending_per_user",
            ),
        ]
    def __str__(self): return self.name

class Review(models.Model):
    professional = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name='reviews_received')
    appointment = models.OneToOneField(Appointment, on_delete=models.CASCADE)
    rating = models.PositiveSmallIntegerField()
    comment = models.CharField(max_length=300)
    status = models.CharField(max_length=20, choices=[("Pendiente","Pendiente"),("Aprobado","Aprobado")], default="Pendiente")
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.CheckConstraint(condition=Q(rating__gte=1, rating__lte=5), name="review_rating_range")]

class ProfessionalService(models.Model):
    """Procedimientos que ofrece cada profesional (catálogo = Service)."""
    professional = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="offered_services")
    service = models.ForeignKey(Service, on_delete=models.PROTECT, related_name="offered_by")
    price = models.PositiveIntegerField("precio propio CLP", null=True, blank=True)
    active = models.BooleanField("activo", default=True)
    class Meta:
        verbose_name = "procedimiento ofrecido"
        constraints = [models.UniqueConstraint(fields=["professional", "service"], name="professional_service_unique")]


class OrdenMedica(models.Model):
    workspace = models.ForeignKey(DemoWorkspace, on_delete=models.CASCADE)
    appointment = models.OneToOneField(Appointment, on_delete=models.PROTECT, null=True, blank=True, related_name="orden")
    patient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="ordenes_recibidas")
    professional = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="ordenes_emitidas")
    service = models.ForeignKey(Service, on_delete=models.PROTECT, related_name="ordenes")
    start_at = models.DateTimeField("inicio")
    end_at = models.DateTimeField("fin")
    transaction = models.ForeignKey(Transaction, on_delete=models.SET_NULL, null=True, blank=True, related_name="ordenes")
    evaluation = models.CharField("evaluación del paciente", max_length=300, blank=True, default="")
    rating = models.PositiveSmallIntegerField("puntuación al profesional", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        verbose_name = "orden médica"
        ordering = ["-start_at"]
        indexes = [models.Index(fields=["professional", "start_at"])]
        constraints = [
            models.CheckConstraint(condition=Q(end_at__gt=models.F("start_at")), name="orden_end_after_start"),
            models.CheckConstraint(condition=Q(rating__isnull=True) | Q(rating__gte=1, rating__lte=5), name="orden_rating_range"),
        ]
    def __str__(self): return f"Orden #{self.pk}"

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
    ADMIN_LEVELS = [('normal','Administrador'),('super_admin','Superadministrador')]
    user = models.OneToOneField(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name='clinical_profile')
    role = models.CharField(max_length=20,choices=ROLES)
    admin_level = models.CharField(max_length=20, choices=ADMIN_LEVELS, default="normal")
    workspace = models.ForeignKey(DemoWorkspace,on_delete=models.PROTECT)
    date_of_birth = models.DateField("fecha de nacimiento", null=True, blank=True)
    phone = models.CharField("teléfono", max_length=30, blank=True, default="")
    address = models.CharField("dirección", max_length=250, blank=True, default="")
    city = models.CharField("comuna/ciudad", max_length=100, blank=True, default="")
    bill_sent = models.BooleanField(default=False)
    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(role="admin") | Q(admin_level="normal"),
                name="super_admin_requires_admin_role",
            ),
        ]
    def __str__(self): return f'{self.user.username} — {self.get_role_display()}'

class UserRoleChange(models.Model):
    workspace = models.ForeignKey(DemoWorkspace, on_delete=models.PROTECT, related_name="role_changes")
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="role_changes_made")
    target_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="role_changes_received")
    previous_role = models.CharField(max_length=20, choices=UserProfile.ROLES)
    new_role = models.CharField(max_length=20, choices=UserProfile.ROLES)
    previous_admin_level = models.CharField(max_length=20, choices=UserProfile.ADMIN_LEVELS)
    new_admin_level = models.CharField(max_length=20, choices=UserProfile.ADMIN_LEVELS)
    changed_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ["-changed_at"]
        constraints = [
            models.CheckConstraint(
                condition=~Q(changed_by=models.F("target_user")),
                name="role_change_actor_not_target",
            ),
        ]
    def __str__(self): return f"{self.changed_by_id} → {self.target_user_id}: {self.new_role}"

class ApplicantDocument(models.Model):
    applicant = models.ForeignKey(Applicant, on_delete=models.PROTECT, related_name="documents")
    document_type = models.CharField("tipo de credencial", max_length=60)
    original_name = models.CharField(max_length=120)
    content_type = models.CharField(max_length=40)
    size = models.PositiveIntegerField()
    mongo_id = models.CharField(max_length=24, unique=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ["uploaded_at"]
        constraints = [
            models.CheckConstraint(condition=Q(size__gt=0), name="applicant_document_size_positive"),
        ]
        verbose_name = "documento de postulación"
    def __str__(self): return f"{self.document_type} · {self.applicant_id}"

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
