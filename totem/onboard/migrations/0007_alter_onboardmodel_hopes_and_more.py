# Generated by Django 4.2.6 on 2023-10-20 20:48

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("onboard", "0006_remove_onboardmodel_circle_general_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="onboardmodel",
            name="hopes",
            field=models.TextField(
                blank=True, null=True, validators=[django.core.validators.MaxLengthValidator(5000)]
            ),
        ),
        migrations.AlterField(
            model_name="onboardmodel",
            name="internal_notes",
            field=models.TextField(
                blank=True, null=True, validators=[django.core.validators.MaxLengthValidator(10000)]
            ),
        ),
        migrations.AlterField(
            model_name="onboardmodel",
            name="suggestions",
            field=models.TextField(
                blank=True, null=True, validators=[django.core.validators.MaxLengthValidator(5000)]
            ),
        ),
    ]