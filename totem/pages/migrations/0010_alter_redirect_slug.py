# Generated by Django 5.0.2 on 2024-02-13 21:51

import totem.utils.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pages', '0009_alter_redirect_slug'),
    ]

    operations = [
        migrations.AlterField(
            model_name='redirect',
            name='slug',
            field=models.SlugField(blank=True, default=totem.utils.models.make_slug, editable=False, unique=True),
        ),
    ]
