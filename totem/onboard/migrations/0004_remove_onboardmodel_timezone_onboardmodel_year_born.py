# Generated by Django 4.2.5 on 2023-10-09 20:08

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("onboard", "0003_onboardmodel_timezone"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="onboardmodel",
            name="timezone",
        ),
        migrations.AddField(
            model_name="onboardmodel",
            name="year_born",
            field=models.IntegerField(blank=True, null=True),
        ),
    ]
