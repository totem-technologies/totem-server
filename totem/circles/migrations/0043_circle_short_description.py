# Generated by Django 5.1.6 on 2025-03-07 22:43

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('circles', '0042_alter_circleevent_cancelled'),
    ]

    operations = [
        migrations.AddField(
            model_name='circle',
            name='short_description',
            field=models.CharField(blank=True, help_text='Short description, max 255 characters', max_length=255),
        ),
    ]
