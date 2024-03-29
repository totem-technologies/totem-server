# Generated by Django 5.0.1 on 2024-01-30 22:17

import django.core.validators
import totem.utils.md
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("circles", "0033_alter_circle_content_alter_circleevent_content"),
    ]

    operations = [
        migrations.AlterField(
            model_name="circleevent",
            name="content",
            field=totem.utils.md.MarkdownField(
                blank=True,
                help_text="Optional description for this specific Circle session. Markdown is supported.",
                max_length=10000,
                null=True,
                validators=[
                    totem.utils.md.MarkdownMixin.validate_markdown,
                    django.core.validators.MaxLengthValidator(10000),
                ],
            ),
        ),
    ]
