# Generated by Django 4.2.4 on 2023-08-24 06:08

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("circles", "0010_alter_circle_slug"),
    ]

    operations = [
        migrations.AddField(
            model_name="circle",
            name="rrule",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]
