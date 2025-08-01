# Generated by Django 5.2.4 on 2025-07-21 09:22

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('garage', '0006_user_client_fiscal_year'),
    ]

    operations = [
        migrations.CreateModel(
            name='VehicleCompany',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('description', models.TextField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('client_garage', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='vehicle_companies', to='garage.clientgarage')),
            ],
        ),
        migrations.CreateModel(
            name='VehicleType',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('description', models.TextField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('client_garage', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='vehicle_types', to='garage.clientgarage')),
            ],
        ),
        migrations.CreateModel(
            name='VehicleModel',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('description', models.TextField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('client_garage', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='vehicle_models', to='garage.clientgarage')),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='models', to='garage.vehiclecompany')),
                ('vehicle_type', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='models', to='garage.vehicletype')),
            ],
        ),
    ]
