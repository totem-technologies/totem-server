# Generated by Django 4.2.4 on 2023-08-31 23:12

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("circles", "0016_alter_circleevent_start"),
    ]

    operations = [
        migrations.AddField(
            model_name="circle",
            name="image",
            field=models.ImageField(blank=True, null=True, upload_to="circles"),
        ),
    ]
