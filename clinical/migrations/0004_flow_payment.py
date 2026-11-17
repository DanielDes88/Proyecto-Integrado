from django.db import migrations, models


def preserve_existing_payment_status(apps, schema_editor):
    Appointment = apps.get_model("clinical", "Appointment")
    Appointment.objects.filter(paid=True).update(payment_status="paid")


class Migration(migrations.Migration):

    dependencies = [
        ("clinical", "0003_clinicaldocument"),
    ]

    operations = [
        migrations.AddField(
            model_name="appointment",
            name="payment_status",
            field=models.CharField(
                choices=[
                    ("pending", "pending"),
                    ("paid", "paid"),
                    ("rejected", "rejected"),
                    ("cancelled", "cancelled"),
                ],
                default="pending",
                max_length=12,
                verbose_name="estado del pago",
            ),
        ),
        migrations.AddField(
            model_name="appointment",
            name="flow_order",
            field=models.CharField(blank=True, default="", max_length=30),
        ),
        migrations.AddField(
            model_name="appointment",
            name="flow_token",
            field=models.CharField(blank=True, max_length=100, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="appointment",
            name="flow_url",
            field=models.URLField(blank=True, default="", max_length=500),
        ),
        migrations.RunPython(preserve_existing_payment_status, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="appointment",
            name="paid",
            field=models.BooleanField(default=False, verbose_name="pago confirmado"),
        ),
    ]
