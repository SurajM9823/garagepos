
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.views import View
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from garage.models import User, FinancialYear, SoftwareInfo
from rest_framework.permissions import AllowAny
from rest_framework.authentication import SessionAuthentication, BasicAuthentication
from django.core.exceptions import ValidationError
from django.contrib import messages
import os
import re
from datetime import datetime

from garage.models import User, FinancialYear, SoftwareInfo, ClientGarage, ClientFiscalYear
# Add to existing imports
from garage.models import TaxSetting, ServiceType, PartCategory, Role
from datetime import date

# Replace the existing admin_setting_views with:
@login_required
def admin_setting_views(request):
    if request.user.is_superuser or request.user.role != 'admin':
        return redirect(f'/{request.user.role}/dashboard/')
    
    client_garage = request.user.client_garage
    if not client_garage:
        messages.error(request, 'No client garage associated with this user.')
        return redirect('admin_dashboard')
    
    tax_setting = TaxSetting.objects.filter(client_garage=client_garage).first()
    fiscal_years = ClientFiscalYear.objects.filter(client_garage=client_garage).order_by('-created_at')
    service_types = ServiceType.objects.filter(client_garage=client_garage).order_by('-created_at')
    part_categories = PartCategory.objects.filter(client_garage=client_garage).order_by('-created_at')
    roles = Role.objects.filter(client_garage=client_garage).order_by('-created_at')
    users = User.objects.filter(client_garage=client_garage).order_by('-date_joined')
    software_info = SoftwareInfo.objects.first()

    context = {
        'user': request.user,
        'client_garage': client_garage,
        'tax_setting': tax_setting,
        'fiscal_years': fiscal_years,
        'service_types': service_types,
        'part_categories': part_categories,
        'roles': roles,
        'users': users,
        'software_info': software_info,
    }
    return render(request, 'admin/setting.html', context)

# Add these new views at the end of the file:
@login_required
def save_general_settings(request):
    if request.user.is_superuser or request.user.role != 'admin':
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    if request.method == 'POST':
        try:
            client_garage = request.user.client_garage
            if not client_garage:
                return JsonResponse({'error': 'No client garage associated'}, status=400)

            client_garage.name = request.POST.get('garage_name')
            client_garage.address = request.POST.get('address')
            client_garage.contact = request.POST.get('phone')
            client_garage.email = request.POST.get('email')
            client_garage.currency = request.POST.get('currency', 'NPR')
            client_garage.low_stock_threshold = int(request.POST.get('low_stock_threshold', 5))
            client_garage.notifications_enabled = request.POST.get('notifications') == 'true'
            client_garage.whatsapp_enabled = request.POST.get('whatsapp') == 'true'

            if 'logo' in request.FILES:
                logo = request.FILES['logo']
                if not logo.content_type.startswith('image/'):
                    return JsonResponse({'error': 'Logo must be an image file'}, status=400)
                if logo.size > 5 * 1024 * 1024:
                    return JsonResponse({'error': 'Logo file size must be under 5MB'}, status=400)
                if client_garage.logo and os.path.isfile(client_garage.logo.path):
                    os.remove(client_garage.logo.path)
                client_garage.logo = logo

            if not client_garage.name:
                return JsonResponse({'error': 'Garage name is required'}, status=400)
            if client_garage.email and not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', client_garage.email):
                return JsonResponse({'error': 'Invalid email format'}, status=400)
            if client_garage.contact and not re.match(r'^\+?[\d\s-]{10,}$', client_garage.contact):
                return JsonResponse({'error': 'Invalid contact number format'}, status=400)

            client_garage.save()
            return JsonResponse({'message': 'General settings updated successfully'}, status=200)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid request method'}, status=400)

@login_required
def save_fiscal_year(request):
    if request.user.is_superuser or request.user.role != 'admin':
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    if request.method == 'POST':
        try:
            client_garage = request.user.client_garage
            if not client_garage:
                return JsonResponse({'error': 'No client garage associated'}, status=400)

            fiscal_year_id = request.POST.get('id')
            name = request.POST.get('name')
            start_date = request.POST.get('start_date')
            end_date = request.POST.get('end_date')
            active = request.POST.get('active') == 'true'

            if not all([name, start_date, end_date]):
                return JsonResponse({'error': 'All fields are required'}, status=400)
            if not re.match(r'^\d{4}/\d{4}$', name):
                return JsonResponse({'error': 'Fiscal year name must be in YYYY/YYYY format'}, status=400)

            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
            if start_date >= end_date:
                return JsonResponse({'error': 'Start date must be before end date'}, status=400)

            if fiscal_year_id:
                fiscal_year = ClientFiscalYear.objects.get(pk=fiscal_year_id, client_garage=client_garage)
                if ClientFiscalYear.objects.filter(client_garage=client_garage, name=name).exclude(pk=fiscal_year_id).exists():
                    return JsonResponse({'error': 'Fiscal year name already exists'}, status=400)
                fiscal_year.name = name
                fiscal_year.start_date = start_date
                fiscal_year.end_date = end_date
                fiscal_year.status = 'active' if active else 'inactive'
                fiscal_year.save()
            else:
                if ClientFiscalYear.objects.filter(client_garage=client_garage, name=name).exists():
                    return JsonResponse({'error': 'Fiscal year name already exists'}, status=400)
                fiscal_year = ClientFiscalYear.objects.create(
                    client_garage=client_garage,
                    name=name,
                    type='fiscal',
                    start_date=start_date,
                    end_date=end_date,
                    status='active' if active else 'inactive'
                )

            return JsonResponse({'message': 'Fiscal year saved successfully'}, status=200)
        except ClientFiscalYear.DoesNotExist:
            return JsonResponse({'error': 'Fiscal year not found'}, status=404)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid request method'}, status=400)

@login_required
def delete_fiscal_year(request):
    if request.user.is_superuser or request.user.role != 'admin':
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    if request.method == 'POST':
        try:
            fiscal_year_id = request.POST.get('id')
            fiscal_year = ClientFiscalYear.objects.get(pk=fiscal_year_id, client_garage=request.user.client_garage)
            if fiscal_year.status == 'active':
                return JsonResponse({'error': 'Cannot delete active fiscal year'}, status=400)
            fiscal_year.delete()
            return JsonResponse({'message': 'Fiscal year deleted successfully'}, status=200)
        except ClientFiscalYear.DoesNotExist:
            return JsonResponse({'error': 'Fiscal year not found'}, status=404)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid request method'}, status=400)

@login_required
def save_tax_settings(request):
    if request.user.is_superuser or request.user.role != 'admin':
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    if request.method == 'POST':
        try:
            client_garage = request.user.client_garage
            if not client_garage:
                return JsonResponse({'error': 'No client garage associated'}, status=400)

            tax_rate = request.POST.get('tax_rate')
            include_in_bill = request.POST.get('include_in_bill') == 'true'

            if not tax_rate:
                return JsonResponse({'error': 'Tax rate is required'}, status=400)
            tax_rate = float(tax_rate)
            if tax_rate < 0 or tax_rate > 100:
                return JsonResponse({'error': 'Tax rate must be between 0 and 100'}, status=400)

            tax_setting = TaxSetting.objects.filter(client_garage=client_garage).first()
            if tax_setting:
                tax_setting.tax_rate = tax_rate
                tax_setting.include_in_bill = include_in_bill
                tax_setting.save()
            else:
                TaxSetting.objects.create(
                    client_garage=client_garage,
                    tax_rate=tax_rate,
                    include_in_bill=include_in_bill
                )

            return JsonResponse({'message': 'Tax settings saved successfully'}, status=200)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid request method'}, status=400)

@login_required
def save_service_type(request):
    if request.user.is_superuser or request.user.role != 'admin':
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    if request.method == 'POST':
        try:
            client_garage = request.user.client_garage
            if not client_garage:
                return JsonResponse({'error': 'No client garage associated'}, status=400)

            service_id = request.POST.get('id')
            name = request.POST.get('name')
            category = request.POST.get('category')
            base_price = request.POST.get('base_price')

            if not all([name, category, base_price]):
                return JsonResponse({'error': 'All fields are required'}, status=400)
            base_price = float(base_price)
            if base_price < 0:
                return JsonResponse({'error': 'Base price cannot be negative'}, status=400)

            if service_id:
                service = ServiceType.objects.get(pk=service_id, client_garage=client_garage)
                if ServiceType.objects.filter(client_garage=client_garage, name=name).exclude(pk=service_id).exists():
                    return JsonResponse({'error': 'Service name already exists'}, status=400)
                service.name = name
                service.category = category
                service.base_price = base_price
                service.save()
            else:
                if ServiceType.objects.filter(client_garage=client_garage, name=name).exists():
                    return JsonResponse({'error': 'Service name already exists'}, status=400)
                ServiceType.objects.create(
                    client_garage=client_garage,
                    name=name,
                    category=category,
                    base_price=base_price
                )

            return JsonResponse({'message': 'Service type saved successfully'}, status=200)
        except ServiceType.DoesNotExist:
            return JsonResponse({'error': 'Service type not found'}, status=404)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid request method'}, status=400)

@login_required
def delete_service_type(request):
    if request.user.is_superuser or request.user.role != 'admin':
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    if request.method == 'POST':
        try:
            service_id = request.POST.get('id')
            service = ServiceType.objects.get(pk=service_id, client_garage=request.user.client_garage)
            service.delete()
            return JsonResponse({'message': 'Service type deleted successfully'}, status=200)
        except ServiceType.DoesNotExist:
            return JsonResponse({'error': 'Service type not found'}, status=404)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid request method'}, status=400)

@login_required
def save_part_category(request):
    if request.user.is_superuser or request.user.role != 'admin':
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    if request.method == 'POST':
        try:
            client_garage = request.user.client_garage
            if not client_garage:
                return JsonResponse({'error': 'No client garage associated'}, status=400)

            category_id = request.POST.get('id')
            name = request.POST.get('name')
            description = request.POST.get('description')

            if not name:
                return JsonResponse({'error': 'Category name is required'}, status=400)

            if category_id:
                category = PartCategory.objects.get(pk=category_id, client_garage=client_garage)
                if PartCategory.objects.filter(client_garage=client_garage, name=name).exclude(pk=category_id).exists():
                    return JsonResponse({'error': 'Category name already exists'}, status=400)
                category.name = name
                category.description = description
                category.save()
            else:
                if PartCategory.objects.filter(client_garage=client_garage, name=name).exists():
                    return JsonResponse({'error': 'Category name already exists'}, status=400)
                PartCategory.objects.create(
                    client_garage=client_garage,
                    name=name,
                    description=description
                )

            return JsonResponse({'message': 'Part category saved successfully'}, status=200)
        except PartCategory.DoesNotExist:
            return JsonResponse({'error': 'Part category not found'}, status=404)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid request method'}, status=400)

@login_required
def delete_part_category(request):
    if request.user.is_superuser or request.user.role != 'admin':
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    if request.method == 'POST':
        try:
            category_id = request.POST.get('id')
            category = PartCategory.objects.get(pk=category_id, client_garage=request.user.client_garage)
            category.delete()
            return JsonResponse({'message': 'Part category deleted successfully'}, status=200)
        except PartCategory.DoesNotExist:
            return JsonResponse({'error': 'Part category not found'}, status=404)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid request method'}, status=400)

@login_required
def save_role(request):
    if request.user.is_superuser or request.user.role != 'admin':
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    if request.method == 'POST':
        try:
            client_garage = request.user.client_garage
            if not client_garage:
                return JsonResponse({'error': 'No client garage associated'}, status=400)

            role_id = request.POST.get('id')
            name = request.POST.get('role')
            description = request.POST.get('description')
            permissions = request.POST.getlist('permissions')

            if not name:
                return JsonResponse({'error': 'Role name is required'}, status=400)

            if role_id:
                role = Role.objects.get(pk=role_id, client_garage=client_garage)
                if Role.objects.filter(client_garage=client_garage, name=name).exclude(pk=role_id).exists():
                    return JsonResponse({'error': 'Role name already exists'}, status=400)
                role.name = name
                role.description = description
                role.permissions = permissions
                role.save()
            else:
                if Role.objects.filter(client_garage=client_garage, name=name).exists():
                    return JsonResponse({'error': 'Role name already exists'}, status=400)
                Role.objects.create(
                    client_garage=client_garage,
                    name=name,
                    description=description,
                    permissions=permissions
                )

            return JsonResponse({'message': 'Role saved successfully'}, status=200)
        except Role.DoesNotExist:
            return JsonResponse({'error': 'Role not found'}, status=404)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid request method'}, status=400)

@login_required
def delete_role(request):
    if request.user.is_superuser or request.user.role != 'admin':
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    if request.method == 'POST':
        try:
            role_id = request.POST.get('id')
            role = Role.objects.get(pk=role_id, client_garage=request.user.client_garage)
            role.delete()
            return JsonResponse({'message': 'Role deleted successfully'}, status=200)
        except Role.DoesNotExist:
            return JsonResponse({'error': 'Role not found'}, status=404)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid request method'}, status=400)

@login_required
def save_user(request):
    if request.user.is_superuser or request.user.role != 'admin':
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    if request.method == 'POST':
        try:
            client_garage = request.user.client_garage
            if not client_garage:
                return JsonResponse({'error': 'No client garage associated'}, status=400)

            user_id = request.POST.get('id')
            name = request.POST.get('name')
            email = request.POST.get('email')
            role = request.POST.get('role')
            password = request.POST.get('password')

            if not all([name, email, role]):
                return JsonResponse({'error': 'Name, email, and role are required'}, status=400)
            if not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', email):
                return JsonResponse({'error': 'Invalid email format'}, status=400)
            if role not in ['staff', 'manager', 'cashier', 'mechanic']:
                return JsonResponse({'error': 'Role must be staff, manager, cashier, or mechanic'}, status=400)
            if password and len(password) < 8:
                return JsonResponse({'error': 'Password must be at least 8 characters long'}, status=400)

            # Get the active financial years
            active_financial_year = FinancialYear.objects.filter(status='active').first()
            active_client_fiscal_year = ClientFiscalYear.objects.filter(client_garage=client_garage, status='active').first()
            if not active_client_fiscal_year and not user_id:
                return JsonResponse({'error': 'No active client fiscal year found for new user'}, status=400)
            if not active_financial_year and not user_id:
                return JsonResponse({'error': 'No active financial year found for new user'}, status=400)

            if user_id:
                user = User.objects.get(pk=user_id, client_garage=client_garage)
                if User.objects.filter(email=email, client_garage=client_garage).exclude(pk=user_id).exists():
                    return JsonResponse({'error': 'Email already exists'}, status=400)
                user.username = name
                user.email = email
                user.role = role
                if password:
                    user.set_password(password)
                    user.plaintext_password = password
                user.save()
            else:
                if User.objects.filter(email=email, client_garage=client_garage).exists():
                    return JsonResponse({'error': 'Email already exists'}, status=400)
                if not password:
                    return JsonResponse({'error': 'Password is required for new users'}, status=400)
                User.objects.create_user(
                    username=name,
                    email=email,
                    password=password,
                    role=role,
                    client_garage=client_garage,
                    financial_year=active_financial_year,
                    client_fiscal_year=active_client_fiscal_year
                )

            return JsonResponse({'message': 'User saved successfully'}, status=200)
        except User.DoesNotExist:
            return JsonResponse({'error': 'User not found'}, status=404)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid request method'}, status=400)

@login_required
def save_other_settings(request):
    if request.user.is_superuser or request.user.role != 'admin':
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    if request.method == 'POST':
        try:
            software_info = SoftwareInfo.objects.first()
            if not software_info:
                return JsonResponse({'error': 'Software info not found'}, status=400)

            software_info.invoice_prefix = request.POST.get('invoice_prefix', 'INV-')
            software_info.language = request.POST.get('language', 'en')
            software_info.backup_frequency = request.POST.get('backup_frequency', 'Weekly')
            software_info.save()

            return JsonResponse({'message': 'Other settings saved successfully'}, status=200)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid request method'}, status=400)