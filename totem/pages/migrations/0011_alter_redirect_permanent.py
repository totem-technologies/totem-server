# Generated by Django 5.1.2 on 2024-10-29 14:38

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pages', '0010_alter_redirect_slug'),
    ]

    operations = [
        migrations.AlterField(
            model_name='redirect',
            name='permanent',
            field=models.BooleanField(default=False, help_text='If true, this redirect will be permanent and changes to the URL will work if the user scans the code again.'),
        ),
    ]
