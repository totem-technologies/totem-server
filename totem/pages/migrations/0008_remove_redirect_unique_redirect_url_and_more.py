# Generated by Django 4.2.5 on 2023-09-19 19:22

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("pages", "0007_redirect_alternate_slug_and_more"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="redirect",
            name="unique_redirect_url",
        ),
        migrations.RemoveConstraint(
            model_name="redirect",
            name="unique_redirect_slug",
        ),
        migrations.RemoveConstraint(
            model_name="redirect",
            name="unique_redirect_alternate_slug",
        ),
    ]
