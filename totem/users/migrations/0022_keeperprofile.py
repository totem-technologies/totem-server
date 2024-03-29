# Generated by Django 4.2.6 on 2023-10-20 20:48

from django.conf import settings
import django.core.validators
from django.db import migrations, models
import django.db.models.deletion
import totem.utils.md


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0021_user_profile_avatar_seed_user_profile_avatar_type"),
    ]

    operations = [
        migrations.CreateModel(
            name="KeeperProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "bio",
                    totem.utils.md.MarkdownField(
                        blank=True,
                        max_length=10000,
                        validators=[
                            totem.utils.md.MarkdownMixin.validate_markdown,
                            django.core.validators.MaxLengthValidator(10000),
                        ],
                    ),
                ),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="keeper_profile",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            bases=(models.Model, totem.utils.md.MarkdownMixin),
        ),
    ]
