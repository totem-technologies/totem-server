# Generated by Django 4.1.8 on 2023-05-22 23:42

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("email", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="waitlist",
            name="name",
            field=models.CharField(default="test", max_length=255),
            preserve_default=False,
        ),
    ]
