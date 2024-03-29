# Generated by Django 4.2.3 on 2023-07-25 04:31

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("circles", "0003_rename_starts_circle_start"),
    ]

    operations = [
        migrations.AddField(
            model_name="circle",
            name="attendees",
            field=models.ManyToManyField(blank=True, related_name="attending", to=settings.AUTH_USER_MODEL),
        ),
    ]
