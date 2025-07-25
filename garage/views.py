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

@login_required
def admin_dashboard(request):
    if request.user.is_superuser or request.user.role != 'admin':
        return redirect(f'/{request.user.role}/dashboard/')
    return render(request, 'admin_dashboard.html', {'user': request.user})

@login_required
def staff_dashboard(request):
    if request.user.is_superuser or request.user.role != 'staff':
        return redirect(f'/{request.user.role}/dashboard/')
    return render(request, 'staff_dashboard.html', {'user': request.user})

def login_page(request):
    return render(request, 'login.html', {'csrf_token': get_token(request)})

@login_required
def add_company_user(request):
    if not request.user.is_superuser:
        return redirect(f'/{request.user.role}/dashboard/')
    return render(request, 'superuser/add_user.html', {'user': request.user})

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

@login_required
def save_financial_year(request):
    if not request.user.is_superuser:
        return redirect(f'/{request.user.role}/dashboard/')
    if request.method == 'POST':
        try:
            name = request.POST.get('fy_name')
            fy_type = request.POST.get('fy_type')
            start_date = request.POST.get('fy_start_date')
            end_date = request.POST.get('fy_end_date')

            if not all([name, fy_type, start_date, end_date]):
                messages.error(request, 'All fields are required.')
                return render(request, 'superuser/superuser_setting.html', {
                    'user': request.user,
                    'financial_years': FinancialYear.objects.all().order_by('-created_at'),
                    'software_info': SoftwareInfo.objects.first()
                })

            # Validate name format (e.g., 2081/2082)
            if not re.match(r'^\d{4}/\d{4}$', name):
                messages.error(request, 'Financial year name must be in the format YYYY/YYYY (e.g., 2081/2082).')
                return render(request, 'superuser/superuser_setting.html', {
                    'user': request.user,
                    'financial_years': FinancialYear.objects.all().order_by('-created_at'),
                    'software_info': SoftwareInfo.objects.first()
                })

            # Validate dates
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
            if start_date >= end_date:
                messages.error(request, 'Start date must be before end date.')
                return render(request, 'superuser/superuser_setting.html', {
                    'user': request.user,
                    'financial_years': FinancialYear.objects.all().order_by('-created_at'),
                    'software_info': SoftwareInfo.objects.first()
                })

            # Check for duplicate name
            if FinancialYear.objects.filter(name=name).exists():
                messages.error(request, 'Financial year name already exists.')
                return render(request, 'superuser/superuser_setting.html', {
                    'user': request.user,
                    'financial_years': FinancialYear.objects.all().order_by('-created_at'),
                    'software_info': SoftwareInfo.objects.first()
                })

            FinancialYear.objects.create(
                name=name,
                type=fy_type,
                start_date=start_date,
                end_date=end_date,
                status='active'  # Default to active
            )
            messages.success(request, 'Financial year saved successfully.')
            return redirect('superuser_setting')
        except ValueError as e:
            messages.error(request, 'Invalid date format.')
            return render(request, 'superuser/superuser_setting.html', {
                'user': request.user,
                'financial_years': FinancialYear.objects.all().order_by('-created_at'),
                'software_info': SoftwareInfo.objects.first()
            })
        except Exception as e:
            messages.error(request, f'Error saving financial year: {str(e)}')
            return render(request, 'superuser/superuser_setting.html', {
                'user': request.user,
                'financial_years': FinancialYear.objects.all().order_by('-created_at'),
                'software_info': SoftwareInfo.objects.first()
            })
    return redirect('superuser_setting')

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
                messages.error(request, 'All fields are required.')
                return render(request, 'superuser/add_user.html', {
                    'user': request.user,
                    'client_garages': ClientGarage.objects.all()
                })

            # Validate email format
            if not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', email):
                messages.error(request, 'Invalid email format.')
                return render(request, 'superuser/add_user.html', {
                    'user': request.user,
                    'client_garages': ClientGarage.objects.all()
                })

            # Validate contact format if provided
            if company_contact and not re.match(r'^\+?[\d\s-]{10,}$', company_contact):
                messages.error(request, 'Invalid contact number format.')
                return render(request, 'superuser/add_user.html', {
                    'user': request.user,
                    'client_garages': ClientGarage.objects.all()
                })

            # Validate username uniqueness
            if User.objects.filter(username=username).exists():
                messages.error(request, 'Username already exists.')
                return render(request, 'superuser/add_user.html', {
                    'user': request.user,
                    'client_garages': ClientGarage.objects.all()
                })

            # Validate email uniqueness
            if User.objects.filter(email=email).exists():
                messages.error(request, 'Email already exists.')
                return render(request, 'superuser/add_user.html', {
                    'user': request.user,
                    'client_garages': ClientGarage.objects.all()
                })

            # Validate password strength
            if len(password) < 8:
                messages.error(request, 'Password must be at least 8 characters long.')
                return render(request, 'superuser/add_user.html', {
                    'user': request.user,
                    'client_garages': ClientGarage.objects.all()
                })

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
                    messages.error(request, 'Logo must be an image file.')
                    return render(request, 'superuser/add_user.html', {
                        'user': request.user,
                        'client_garages': ClientGarage.objects.all()
                    })
                if logo.size > 5 * 1024 * 1024:  # 5MB limit
                    client_garage.delete()
                    messages.error(request, 'Logo file size must be under 5MB.')
                    return render(request, 'superuser/add_user.html', {
                        'user': request.user,
                        'client_garages': ClientGarage.objects.all()
                    })
                client_garage.logo = logo
                client_garage.save()

            # Get active FinancialYear
            financial_year = FinancialYear.objects.filter(status='active').first()
            if not financial_year:
                client_garage.delete()
                messages.error(request, 'No active financial year found.')
                return render(request, 'superuser/add_user.html', {
                    'user': request.user,
                    'client_garages': ClientGarage.objects.all()
                })

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
                start_date=date(current_year, 4, 1),  # Default: April 1
                end_date=date(current_year + 1, 3, 31),  # Default: March 31 next year
                status='active'
            )

            messages.success(request, 'Client company and admin user created successfully.')
            return redirect('add_company_user')
        except Exception as e:
            messages.error(request, f'Error creating client company: {str(e)}')
            return render(request, 'superuser/add_user.html', {
                'user': request.user,
                'client_garages': ClientGarage.objects.all()
            })
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