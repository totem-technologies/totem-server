# Generated by Django 4.2.4 on 2023-09-04 08:27

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0013_user_timezone"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="timezone",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]
