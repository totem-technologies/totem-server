# Generated by Django 5.1.8 on 2025-05-07 22:51

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='fcmdevice',
            name='device_id',
        ),
        migrations.RemoveField(
            model_name='fcmdevice',
            name='device_type',
        ),
    ]
