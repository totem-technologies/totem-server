# Generated by Django 4.2.3 on 2023-07-25 03:58

from django.db import migrations, models
import totem.email.utils


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0002_user_api_key"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="email",
            field=models.EmailField(
                max_length=254,
                unique=True,
                validators=[totem.email.utils.validate_email_blocked],
                verbose_name="email address",
            ),
        ),
    ]
