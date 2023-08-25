# Generated by Django 4.2.4 on 2023-08-25 19:34

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("circles", "0014_circleevent_cancelled"),
    ]

    operations = [
        migrations.AlterField(
            model_name="circle",
            name="price",
            field=models.IntegerField(
                default=0,
                help_text="Price in USD dollars. If you want to offer this Circle for free, enter 0.",
                validators=[
                    django.core.validators.MinValueValidator(0, message="Price must be greater than or equal to 0"),
                    django.core.validators.MaxValueValidator(1000, message="Price must be less than or equal to 1000"),
                ],
                verbose_name="Price (USD)",
            ),
        ),
    ]
