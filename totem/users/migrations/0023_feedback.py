# Generated by Django 4.2.6 on 2023-11-02 21:52

from django.conf import settings
import django.core.validators
from django.db import migrations, models
import django.db.models.deletion
import totem.utils.fields


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0022_keeperprofile"),
    ]

    operations = [
        migrations.CreateModel(
            name="Feedback",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("email", models.EmailField(blank=True, max_length=254, null=True, verbose_name="Email Address")),
                (
                    "message",
                    totem.utils.fields.MaxLengthTextField(
                        max_length=10000,
                        validators=[django.core.validators.MaxLengthValidator(10000)],
                        verbose_name="Feedback",
                    ),
                ),
                ("date_created", models.DateTimeField(auto_now_add=True)),
                (
                    "user",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="feedback",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
    ]
