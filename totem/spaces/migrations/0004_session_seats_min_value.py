from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ("spaces", "0003_session_ended_at"),
    ]

    operations = [
        migrations.AlterField(
            model_name="session",
            name="seats",
            field=models.IntegerField(
                default=8,
                validators=[django.core.validators.MinValueValidator(1)],
            ),
        ),
    ]
