# -*- coding: utf-8 -*-
# Generated by Django 1.11 on 2017-06-03 12:22


from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('committees', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='committee',
            name='joint',
            field=models.BooleanField(default=False, verbose_name='Joint committee?'),
        ),
    ]
