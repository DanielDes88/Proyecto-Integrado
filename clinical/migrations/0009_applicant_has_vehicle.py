from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("clinical", "0008_userrolechange"),
    ]

    operations = [
        migrations.AddField(
            model_name="applicant",
            name="has_vehicle",
            field=models.BooleanField(default=False, verbose_name="dispone de vehículo propio"),
        ),
    ]
