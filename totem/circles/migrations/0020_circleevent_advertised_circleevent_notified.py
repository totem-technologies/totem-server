# Generated by Django 4.2.4 on 2023-09-04 08:19

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("circles", "0019_circleevent_joined_circleevent_meeting_url_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="circleevent",
            name="advertised",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="circleevent",
            name="notified",
            field=models.BooleanField(default=False),
        ),
    ]
