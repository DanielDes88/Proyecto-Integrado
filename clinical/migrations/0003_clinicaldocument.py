import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("clinical", "0002_appointment_patient_appointment_professional_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ClinicalDocument",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("category", models.CharField(choices=[("Receta médica", "Receta médica"), ("Orden médica", "Orden médica"), ("Diagnóstico", "Diagnóstico"), ("Examen", "Examen"), ("Otro", "Otro")], max_length=30)),
                ("original_name", models.CharField(max_length=120)),
                ("content_type", models.CharField(max_length=40)),
                ("size", models.PositiveIntegerField()),
                ("mongo_id", models.CharField(max_length=24, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("appointment", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="documents", to="clinical.appointment")),
                ("patient", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="clinical_documents", to=settings.AUTH_USER_MODEL)),
                ("uploaded_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="uploaded_clinical_documents", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
