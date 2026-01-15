from django.db import migrations


class Migration(migrations.Migration):
    """Historical migration - circles to spaces rename completed.

    This migration originally renamed all circles_* tables to spaces_*.
    It is now a no-op since all environments have been migrated.
    """

    dependencies = [
        ("spaces", "0001_initial"),
    ]

    operations = []
