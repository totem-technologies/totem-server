# Generated by Django 5.1.5 on 2025-01-26 01:08

import django.core.validators
import totem.utils.md
import totem.utils.models
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='BlogPost',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date_created', models.DateTimeField(auto_now_add=True)),
                ('date_modified', models.DateTimeField(auto_now=True)),
                ('slug', models.SlugField(blank=True, default=totem.utils.models.make_slug, editable=False, unique=True)),
                ('title', models.CharField(max_length=255)),
                ('header_image', models.ImageField(blank=True, help_text='Header image for blog post (PNG, JPG, max 5MB)', upload_to='blog/headers/%Y/%m/%d/')),
                ('content', totem.utils.md.MarkdownField(help_text='Markdown content for the blog post', max_length=10000, validators=[totem.utils.md.MarkdownMixin.validate_markdown, django.core.validators.MaxLengthValidator(10000)])),
                ('date_published', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'ordering': ['-date_published'],
            },
            bases=(totem.utils.models.AdminURLMixin, totem.utils.md.MarkdownMixin, models.Model),
        ),
    ]
