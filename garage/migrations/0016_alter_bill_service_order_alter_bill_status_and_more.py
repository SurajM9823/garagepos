# Generated by Django 5.2.4 on 2025-07-23 21:09

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('garage', '0015_serviceorderitem'),
    ]

    operations = [
        migrations.AlterField(
            model_name='bill',
            name='service_order',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='garage.serviceorder'),
        ),
        migrations.AlterField(
            model_name='bill',
            name='status',
            field=models.CharField(choices=[('Pending', 'Pending'), ('Generated (In Progress)', 'Generated (In Progress)'), ('Completed', 'Completed'), ('Credit', 'Credit')], default='Pending', max_length=30),
        ),
        migrations.AlterField(
            model_name='bill',
            name='vehicle',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='garage.vehicle'),
        ),
    ]
