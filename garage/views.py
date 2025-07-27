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
import logging
import re
from datetime import date, datetime

logger = logging.getLogger(__name__)
from garage.models import User, FinancialYear, SoftwareInfo, ClientGarage, ClientFiscalYear


def get_csrf_token(request):
    return JsonResponse({'csrfToken': get_token(request)})

class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = [SessionAuthentication, BasicAuthentication]

    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            if user.is_superuser:
                redirect_url = '/superuser/dashboard/'
            else:
                redirect_url = f'/{user.role}/dashboard/'
            return Response({
                'message': 'Login successful',
                'role': user.role,
                'redirect': redirect_url
            }, status=status.HTTP_200_OK)
        return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)

class LogoutView(APIView):
    def post(self, request):
        logout(request)
        return Response({'message': 'Logout successful'}, status=status.HTTP_200_OK)

@login_required
def superuser_dashboard(request):
    if not request.user.is_superuser:
        return redirect(f'/{request.user.role}/dashboard/')
    return render(request, 'super_dash.html', {'user': request.user})

from django.shortcuts import redirect, render
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from datetime import timedelta
from garage.models import Vehicle, ServiceOrder, Bill, Part, User, ClientGarage, ClientFiscalYear
from django.db.models import Sum, Count
from django.db import IntegrityError, models

@login_required
def admin_dashboard(request):
    if request.user.is_superuser or request.user.role != 'admin':
        return redirect(f'/{request.user.role}/dashboard/')
    
    client_garage = request.user.client_garage
    fiscal_year = request.user.client_fiscal_year
    today = timezone.now().date()

    # Filter by date (today, week, month)
    date_filter = request.GET.get('date-filter', 'today')
    if date_filter == 'week':
        start_date = today - timedelta(days=today.weekday())
    elif date_filter == 'month':
        start_date = today.replace(day=1)
    else:
        start_date = today

    # Stats
    bikes_today = Vehicle.objects.filter(
        client_garage=client_garage,
        created_at__date__gte=start_date,
        created_at__date__lte=today
    ).count()

    ongoing_services = ServiceOrder.objects.filter(
        client_garage=client_garage,
        status__in=['in-progress', 'waiting-assignment'],
        created_date__gte=start_date,
        created_date__lte=today
    ).count()

    pending_bills = Bill.objects.filter(
        client_garage=client_garage,
        status='Pending',
        created_at__date__gte=start_date,
        created_at__date__lte=today
    ).count()

    low_stock_alerts = Part.objects.filter(
        client_garage=client_garage,
        in_stock__lte=models.F('min_stock')
    ).count()

    income_today = Bill.objects.filter(
        client_garage=client_garage,
        status='Completed',
        created_at__date__gte=start_date,
        created_at__date__lte=today
    ).aggregate(total=Sum('total'))['total'] or 0.00

    active_staff = User.objects.filter(
        client_garage=client_garage,
        is_active=True,
        role__in=['staff', 'manager', 'cashier', 'mechanic']
    ).count()

    # Ongoing Services List
    ongoing_services_list = ServiceOrder.objects.filter(
        client_garage=client_garage,
        status__in=['in-progress', 'waiting-assignment'],
        created_date__gte=start_date,
        created_date__lte=today
    ).select_related('vehicle', 'customer').prefetch_related('mechanics')[:3]

    # Recent Activity (simplified; you can expand with more models)
    recent_activities = []
    recent_bills = Bill.objects.filter(
        client_garage=client_garage,
        created_at__date__gte=start_date,
        created_at__date__lte=today
    ).select_related('vehicle')[:2]
    for bill in recent_bills:
        recent_activities.append({
            'description': f"Bill #{bill.bill_no} paid - {client_garage.currency}{bill.total}",
            'time': bill.created_at.strftime('%I:%M %p'),
            'color': 'green'
        })

    recent_service_orders = ServiceOrder.objects.filter(
        client_garage=client_garage,
        created_date__gte=start_date,
        created_date__lte=today
    ).select_related('vehicle')[:2]
    for so in recent_service_orders:
        recent_activities.append({
            'description': f"Vehicle {so.vehicle.vehicle_number} service {'completed' if so.status == 'completed' else 'started'}",
            'time': so.created_at.strftime('%I:%M %p'),
            'color': 'blue' if so.status != 'completed' else 'green'
        })

    recent_parts = Part.objects.filter(
        client_garage=client_garage,
        last_movement__gte=start_date,
        last_movement__lte=today
    )[:1]
    for part in recent_parts:
        if part.in_stock <= part.min_stock:
            recent_activities.append({
                'description': f"Low stock alert: {part.name}",
                'time': part.updated_at.strftime('%I:%M %p'),
                'color': 'yellow'
            })

    # Financial Years
    financial_years = ClientFiscalYear.objects.filter(client_garage=client_garage).order_by('-created_at')

    context = {
        'user': request.user,
        'client_garage': client_garage,
        'bikes_today': bikes_today,
        'ongoing_services': ongoing_services,
        'pending_bills': pending_bills,
        'low_stock_alerts': low_stock_alerts,
        'income_today': income_today,
        'active_staff': active_staff,
        'ongoing_services_list': ongoing_services_list,
        'recent_activities': sorted(recent_activities, key=lambda x: x['time'], reverse=True)[:5],
        'financial_years': financial_years,
        'date_filter': date_filter,
        'currency': client_garage.currency,
    }
    return render(request, 'admin_dashboard.html', context)

@login_required
def staff_dashboard(request):
    if request.user.is_superuser or request.user.role != 'staff':
        return redirect(f'/{request.user.role}/dashboard/')
    return render(request, 'staff_dashboard.html', {'user': request.user})

def login_page(request):
    return render(request, 'login.html', {'csrf_token': get_token(request)})




@login_required
def superuser_setting(request):
    if not request.user.is_superuser:
        return redirect(f'/{request.user.role}/dashboard/')
    financial_years = FinancialYear.objects.all().order_by('-created_at')
    software_info = SoftwareInfo.objects.first()
    context = {
        'user': request.user,
        'financial_years': financial_years,
        'software_info': software_info,
    }
    return render(request, 'superuser/superuser_setting.html', context)

from django.http import JsonResponse

@login_required
def save_financial_year(request):
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Unauthorized'}, status=403) if request.headers.get('X-Requested-With') == 'XMLHttpRequest' else redirect(f'/{request.user.role}/dashboard/')
    
    if request.method == 'POST':
        try:
            logger.debug(f"POST Data: {request.POST}")
            name = request.POST.get('fy_name')
            fy_type = request.POST.get('fy_type')
            start_date = request.POST.get('fy_start_date')
            end_date = request.POST.get('fy_end_date')

            logger.debug(f"Raw Start Date: '{start_date}'")
            logger.debug(f"Raw End Date: '{end_date}'")

            context = {
                'user': request.user,
                'financial_years': FinancialYear.objects.all().order_by('-created_at'),
                'software_info': SoftwareInfo.objects.first()
            }

            if not all([name, fy_type, start_date, end_date]):
                error_msg = 'All fields are required.'
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'error': error_msg}, status=400)
                messages.error(request, error_msg)
                return render(request, 'superuser/superuser_setting.html', context)

            # Update regex to accept YYYY/YY (e.g., 2081/82)
            if not re.match(r'^\d{4}/\d{2}$', name):
                error_msg = 'Financial year name must be in the format YYYY/YY (e.g., 2081/82).'
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'error': error_msg}, status=400)
                messages.error(request, error_msg)
                return render(request, 'superuser/superuser_setting.html', context)

            start_date = datetime.strptime(start_date.strip(), '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date.strip(), '%Y-%m-%d').date()
            if start_date >= end_date:
                error_msg = 'Start date must be before end date.'
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'error': error_msg}, status=400)
                messages.error(request, error_msg)
                return render(request, 'superuser/superuser_setting.html', context)

            if FinancialYear.objects.filter(name=name).exists():
                error_msg = 'Financial year name already exists.'
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'error': error_msg}, status=400)
                messages.error(request, error_msg)
                return render(request, 'superuser/superuser_setting.html', context)

            financial_year = FinancialYear.objects.create(
                name=name,
                type=fy_type,
                start_date=start_date,
                end_date=end_date,
                status='active'
            )
            logger.info(f"Created FinancialYear: {financial_year.id}, {financial_year.name}")

            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': True, 'message': 'Financial year saved successfully.'}, status=200)
            messages.success(request, 'Financial year saved successfully.')
            return redirect('superuser_setting')
        
        except ValueError as e:
            logger.error(f"ValueError: {str(e)}")
            error_msg = f'Invalid date format or data: {str(e)}'
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'error': error_msg}, status=400)
            messages.error(request, error_msg)
            return render(request, 'superuser/superuser_setting.html', context)
        except IntegrityError as e:
            logger.error(f"IntegrityError: {str(e)}")
            error_msg = f'Database integrity error: {str(e)}'
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'error': error_msg}, status=400)
            messages.error(request, error_msg)
            return render(request, 'superuser/superuser_setting.html', context)
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}")
            error_msg = f'Error saving financial year: {str(e)}'
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'error': error_msg}, status=500)
            messages.error(request, error_msg)
            return render(request, 'superuser/superuser_setting.html', context)
    
    return JsonResponse({'error': 'Invalid request method'}, status=400) if request.headers.get('X-Requested-With') == 'XMLHttpRequest' else redirect('superuser_setting')

@login_required
def change_password(request):
    if not request.user.is_superuser:
        return redirect(f'/{request.user.role}/dashboard/')
    if request.method == 'POST':
        try:
            new_password = request.POST.get('new_password')
            confirm_password = request.POST.get('confirm_password')

            if not new_password or not confirm_password:
                messages.error(request, 'Both password fields are required.')
                return render(request, 'superuser/superuser_setting.html', {
                    'user': request.user,
                    'financial_years': FinancialYear.objects.all().order_by('-created_at'),
                    'software_info': SoftwareInfo.objects.first()
                })

            if new_password != confirm_password:
                messages.error(request, 'Passwords do not match.')
                return render(request, 'superuser/superuser_setting.html', {
                    'user': request.user,
                    'financial_years': FinancialYear.objects.all().order_by('-created_at'),
                    'software_info': SoftwareInfo.objects.first()
                })

            # Basic password strength validation
            if len(new_password) < 8:
                messages.error(request, 'Password must be at least 8 characters long.')
                return render(request, 'superuser/superuser_setting.html', {
                    'user': request.user,
                    'financial_years': FinancialYear.objects.all().order_by('-created_at'),
                    'software_info': SoftwareInfo.objects.first()
                })

            user = request.user
            user.set_password(new_password)  # Update hashed password
            user.plaintext_password = new_password  # Update plaintext password
            user.save()
            update_session_auth_hash(request, user)  # Update session to keep user logged in
            messages.success(request, 'Password changed successfully.')
            return redirect('superuser_setting')
        except Exception as e:
            messages.error(request, f'Error changing password: {str(e)}')
            return render(request, 'superuser/superuser_setting.html', {
                'user': request.user,
                'financial_years': FinancialYear.objects.all().order_by('-created_at'),
                'software_info': SoftwareInfo.objects.first()
            })
    return redirect('superuser_setting')

@login_required
def update_software_info(request):
    if not request.user.is_superuser:
        return redirect(f'/{request.user.role}/dashboard/')
    if request.method == 'POST':
        try:
            software_info = SoftwareInfo.objects.first() or SoftwareInfo()
            name = request.POST.get('software_name')
            email = request.POST.get('software_email')
            phone = request.POST.get('software_phone')
            address = request.POST.get('software_address')
            description = request.POST.get('software_description')

            if not name:
                messages.error(request, 'Software name is required.')
                return render(request, 'superuser/superuser_setting.html', {
                    'user': request.user,
                    'financial_years': FinancialYear.objects.all().order_by('-created_at'),
                    'software_info': SoftwareInfo.objects.first()
                })

            # Validate email format if provided
            if email and not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', email):
                messages.error(request, 'Invalid email format.')
                return render(request, 'superuser/superuser_setting.html', {
                    'user': request.user,
                    'financial_years': FinancialYear.objects.all().order_by('-created_at'),
                    'software_info': SoftwareInfo.objects.first()
                })

            # Validate phone format if provided
            if phone and not re.match(r'^\+?[\d\s-]{10,}$', phone):
                messages.error(request, 'Invalid phone number format.')
                return render(request, 'superuser/superuser_setting.html', {
                    'user': request.user,
                    'financial_years': FinancialYear.objects.all().order_by('-created_at'),
                    'software_info': SoftwareInfo.objects.first()
                })

            software_info.name = name
            software_info.email = email
            software_info.phone = phone
            software_info.address = address
            software_info.description = description

            if 'software_logo' in request.FILES:
                # Validate file type and size
                logo = request.FILES['software_logo']
                if not logo.content_type.startswith('image/'):
                    messages.error(request, 'Logo must be an image file.')
                    return render(request, 'superuser/superuser_setting.html', {
                        'user': request.user,
                        'financial_years': FinancialYear.objects.all().order_by('-created_at'),
                        'software_info': SoftwareInfo.objects.first()
                    })
                if logo.size > 5 * 1024 * 1024:  # 5MB limit
                    messages.error(request, 'Logo file size must be under 5MB.')
                    return render(request, 'superuser/superuser_setting.html', {
                        'user': request.user,
                        'financial_years': FinancialYear.objects.all().order_by('-created_at'),
                        'software_info': SoftwareInfo.objects.first()
                    })
                # Delete old logo if exists
                if software_info.logo and os.path.isfile(software_info.logo.path):
                    os.remove(software_info.logo.path)
                software_info.logo = logo

            software_info.save()
            messages.success(request, 'Software information updated successfully.')
            return redirect('superuser_setting')
        except Exception as e:
            messages.error(request, f'Error updating software info: {str(e)}')
            return render(request, 'superuser/superuser_setting.html', {
                'user': request.user,
                'financial_years': FinancialYear.objects.all().order_by('-created_at'),
                'software_info': SoftwareInfo.objects.first()
            })
    return redirect('superuser_setting')

@login_required
def toggle_financial_year_status(request):
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    if request.method == 'POST':
        try:
            fy_id = request.POST.get('fy_id')
            financial_year = FinancialYear.objects.get(pk=fy_id)
            new_status = 'active' if financial_year.status == 'inactive' else 'inactive'
            financial_year.status = new_status
            financial_year.save()  # The save method will handle deactivating others if active
            messages.success(request, f'Financial year {financial_year.name} set to {new_status}.')
            return JsonResponse({'message': 'Status updated successfully'}, status=200)
        except FinancialYear.DoesNotExist:
            return JsonResponse({'error': 'Financial year not found'}, status=404)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid request method'}, status=400)


@login_required
def add_company_user(request):
    if not request.user.is_superuser:
        return redirect(f'/{request.user.role}/dashboard/')
    if request.method == 'POST':
        try:
            # Log the request data for debugging
            print("POST Data:", request.POST)
            print("FILES:", request.FILES)

            # Client company data
            company_name = request.POST.get('company_name')
            company_address = request.POST.get('company_address')
            company_contact = request.POST.get('company_contact')
            # Admin user data
            username = request.POST.get('username')
            email = request.POST.get('email')
            password = request.POST.get('password')

            # Validate required fields
            if not all([company_name, username, email, password]):
                return JsonResponse({'error': 'All fields are required'}, status=400)

            # Validate email format
            if not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', email):
                return JsonResponse({'error': 'Invalid email format'}, status=400)

            # Validate contact format if provided
            if company_contact and not re.match(r'^\+?[\d\s-]{10,}$', company_contact):
                return JsonResponse({'error': 'Invalid contact number format'}, status=400)

            # Validate username uniqueness
            if User.objects.filter(username=username).exists():
                return JsonResponse({'error': 'Username already exists'}, status=400)

            # Validate email uniqueness
            if User.objects.filter(email=email).exists():
                return JsonResponse({'error': 'Email already exists'}, status=400)

            # Validate password strength
            if len(password) < 8:
                return JsonResponse({'error': 'Password must be at least 8 characters long'}, status=400)

            # Create ClientGarage
            client_garage = ClientGarage.objects.create(
                name=company_name,
                address=company_address,
                contact=company_contact
            )

            # Handle logo upload
            if 'company_logo' in request.FILES:
                logo = request.FILES['company_logo']
                if not logo.content_type.startswith('image/'):
                    client_garage.delete()
                    return JsonResponse({'error': 'Logo must be an image file'}, status=400)
                if logo.size > 5 * 1024 * 1024:  # 5MB limit
                    client_garage.delete()
                    return JsonResponse({'error': 'Logo file size must be under 5MB'}, status=400)
                client_garage.logo = logo
                client_garage.save()

            # Get active FinancialYear
            financial_year = FinancialYear.objects.filter(status='active').first()
            if not financial_year:
                client_garage.delete()
                return JsonResponse({'error': 'No active financial year found'}, status=400)

            # Create admin User
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                role='admin',
                client_garage=client_garage,
                financial_year=financial_year
            )

            # Create default ClientFiscalYear
            current_year = datetime.now().year
            ClientFiscalYear.objects.create(
                client_garage=client_garage,
                name=f"{current_year}/{current_year + 1}",
                type='fiscal',
                start_date=date(current_year, 4, 1),
                end_date=date(current_year + 1, 3, 31),
                status='active'
            )

            return JsonResponse({'message': 'Client company and admin user created successfully'}, status=200)
        except Exception as e:
            print("Exception:", str(e))
            return JsonResponse({'error': str(e)}, status=500)
    return render(request, 'superuser/add_user.html', {
        'user': request.user,
        'client_garages': ClientGarage.objects.all()
    })

@login_required
def edit_client_company(request):
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    if request.method == 'POST':
        try:
            client_id = request.POST.get('client_id')
            client_garage = ClientGarage.objects.get(pk=client_id)
            client_garage.name = request.POST.get('company_name')
            client_garage.address = request.POST.get('company_address')
            client_garage.contact = request.POST.get('company_contact')

            # Validate required fields
            if not client_garage.name:
                return JsonResponse({'error': 'Company name is required'}, status=400)

            # Validate contact format if provided
            if client_garage.contact and not re.match(r'^\+?[\d\s-]{10,}$', client_garage.contact):
                return JsonResponse({'error': 'Invalid contact number format'}, status=400)

            # Handle logo upload
            if 'company_logo' in request.FILES:
                logo = request.FILES['company_logo']
                if not logo.content_type.startswith('image/'):
                    return JsonResponse({'error': 'Logo must be an image file'}, status=400)
                if logo.size > 5 * 1024 * 1024:
                    return JsonResponse({'error': 'Logo file size must be under 5MB'}, status=400)
                if client_garage.logo and os.path.isfile(client_garage.logo.path):
                    os.remove(client_garage.logo.path)
                client_garage.logo = logo

            client_garage.save()
            # Update associated user's email
            user = User.objects.get(client_garage=client_garage, role='admin')
            new_email = request.POST.get('email')
            if new_email and new_email != user.email:
                if User.objects.filter(email=new_email).exclude(pk=user.pk).exists():
                    return JsonResponse({'error': 'Email already exists'}, status=400)
                if not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', new_email):
                    return JsonResponse({'error': 'Invalid email format'}, status=400)
                user.email = new_email
                user.save()

            # Update status
            new_status = request.POST.get('status')
            if new_status in ['active', 'inactive']:
                user.is_active = (new_status == 'active')
                user.save()

            messages.success(request, 'Client company updated successfully.')
            return JsonResponse({'message': 'Client company updated successfully'}, status=200)
        except ClientGarage.DoesNotExist:
            return JsonResponse({'error': 'Client company not found'}, status=404)
        except User.DoesNotExist:
            return JsonResponse({'error': 'Associated admin user not found'}, status=404)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid request method'}, status=400)

@login_required
def toggle_client_user_status(request):
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    if request.method == 'POST':
        try:
            user_id = request.POST.get('user_id')
            user = User.objects.get(pk=user_id)
            user.is_active = not user.is_active
            user.save()
            status_text = 'active' if user.is_active else 'inactive'
            messages.success(request, f'User {user.username} set to {status_text}.')
            return JsonResponse({'message': 'Status updated successfully', 'status': status_text}, status=200)
        except User.DoesNotExist:
            return JsonResponse({'error': 'User not found'}, status=404)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid request method'}, status=400)

@login_required
def reset_client_password(request):
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    if request.method == 'POST':
        try:
            user_id = request.POST.get('user_id')
            new_password = request.POST.get('new_password')
            confirm_password = request.POST.get('confirm_password')

            if not new_password or not confirm_password:
                return JsonResponse({'error': 'Both password fields are required'}, status=400)
            if new_password != confirm_password:
                return JsonResponse({'error': 'Passwords do not match'}, status=400)
            if len(new_password) < 8:
                return JsonResponse({'error': 'Password must be at least 8 characters long'}, status=400)

            user = User.objects.get(pk=user_id)
            user.set_password(new_password)
            user.plaintext_password = new_password
            user.save()
            update_session_auth_hash(request, user) if user == request.user else None
            messages.success(request, f'Password for {user.username} reset successfully.')
            return JsonResponse({'message': 'Password reset successfully'}, status=200)
        except User.DoesNotExist:
            return JsonResponse({'error': 'User not found'}, status=404)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid request method'}, status=400)