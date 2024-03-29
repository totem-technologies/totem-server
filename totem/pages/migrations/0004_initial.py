# Generated by Django 4.2.5 on 2023-09-17 22:14

from django.db import migrations, models
import totem.utils.models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Redirect",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date_created", models.DateTimeField(auto_now_add=True)),
                ("date_modified", models.DateTimeField(auto_now=True)),
                (
                    "slug",
                    models.SlugField(blank=True, default=totem.utils.models.make_slug, editable=False, unique=True),
                ),
                ("url", models.CharField()),
                ("permanent", models.BooleanField(default=True)),
                ("notes", models.TextField(blank=True)),
                ("count", models.BigIntegerField(default=0)),
            ],
            options={
                "verbose_name": "Redirect",
                "verbose_name_plural": "Redirects",
                "ordering": ["url"],
                "indexes": [models.Index(fields=["url"], name="pages_redir_url_96914e_idx")],
            },
        ),
        migrations.AddConstraint(
            model_name="redirect",
            constraint=models.UniqueConstraint(fields=("url",), name="unique_redirect_url"),
        ),
        migrations.AddConstraint(
            model_name="redirect",
            constraint=models.UniqueConstraint(fields=("slug",), name="unique_redirect_slug"),
        ),
    ]
