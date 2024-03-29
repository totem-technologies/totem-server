# Generated by Django 4.2.3 on 2023-08-08 22:04

from django.db import migrations
from totem.utils.models import make_slug


def gen_uuid(apps, schema_editor):
    MyModel = apps.get_model("users", "User")
    for row in MyModel.objects.all():
        row.slug = make_slug()
        row.save(update_fields=["slug"])


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0008_alter_user_options_user_slug"),
    ]

    operations = [
        # omit reverse_code=... if you don't want the migration to be reversible.
        migrations.RunPython(gen_uuid, reverse_code=migrations.RunPython.noop),
    ]
