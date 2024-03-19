# Generated by Django 5.0.3 on 2024-03-19 02:22

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0034_keeperprofile_username'),
    ]

    operations = [
        migrations.AlterField(
            model_name='keeperprofile',
            name='username',
            field=models.CharField(db_index=True, help_text='Your unique username.', max_length=30, null=True, unique=True),
        ),
    ]
