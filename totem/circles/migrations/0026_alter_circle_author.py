# Generated by Django 4.2.6 on 2023-10-20 03:10

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("circles", "0025_alter_circle_image"),
    ]

    operations = [
        migrations.AlterField(
            model_name="circle",
            name="author",
            field=models.ForeignKey(
                limit_choices_to={"is_staff": True},
                on_delete=django.db.models.deletion.CASCADE,
                related_name="created_circles",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
