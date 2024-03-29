# Generated by Django 4.2.5 on 2023-10-03 21:03

from django.db import migrations
import imagekit.models.fields
import totem.circles.models


class Migration(migrations.Migration):
    dependencies = [
        ("circles", "0024_alter_circle_image"),
    ]

    operations = [
        migrations.AlterField(
            model_name="circle",
            name="image",
            field=imagekit.models.fields.ProcessedImageField(
                blank=True,
                help_text="Image for the Circle, must be under 5mb",
                null=True,
                upload_to=totem.circles.models.upload_to_id_image,
            ),
        ),
    ]
