from django.db import migrations


def create_mobile_application(apps, schema_editor):
    Application = apps.get_model("oauth2_provider", "Application")
    Application.objects.get_or_create(
        name="Totem Mobile",
        defaults={
            "client_type": "public",
            "authorization_grant_type": "password",
            "skip_authorization": True,
        },
    )


def remove_mobile_application(apps, schema_editor):
    Application = apps.get_model("oauth2_provider", "Application")
    Application.objects.filter(name="Totem Mobile").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("oauth2_provider", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_mobile_application, remove_mobile_application),
    ]
