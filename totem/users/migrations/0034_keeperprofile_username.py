# Generated by Django 5.0.3 on 2024-03-19 02:08

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0033_alter_keeperprofile_instagram_username_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='keeperprofile',
            name='username',
            field=models.CharField(db_index=True, max_length=30, null=True, unique=True),
        ),
    ]
