from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0002_alter_user_managers"),
    ]

    operations = [
        migrations.DeleteModel(
            name="RefreshToken",
        ),
    ]
