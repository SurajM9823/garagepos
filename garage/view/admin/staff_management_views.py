from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.db.models import Count, Avg, Q, Sum
from django.core.exceptions import ValidationError
from django.contrib import messages
from garage.models import User, ClientGarage, FinancialYear, ClientFiscalYear, ServiceOrder, StaffPayroll, StaffAttendance
import re
import os
from datetime import datetime, date, timedelta
import json
from decimal import Decimal
import csv
from io import StringIO

@login_required
def staff_management(request):
    if request.user.is_superuser or request.user.role != 'admin':
        return redirect(f'/{request.user.role}/dashboard/')
    
    client_garage = request.user.client_garage
    if not client_garage:
        messages.error(request, 'No client garage associated with this user.')
        return redirect('admin_dashboard')

    context = {
        'user': request.user,
        'client_garage': client_garage,
    }
    return render(request, 'admin/staff_management.html', context)

@login_required
def get_staff_list(request):
    if request.user.is_superuser or request.user.role != 'admin':
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    client_garage = request.user.client_garage
    if not client_garage:
        return JsonResponse({'error': 'No client garage associated'}, status=400)

    search_term = request.GET.get('search', '')
    staff = User.objects.filter(
        client_garage=client_garage,
        role__in=['staff', 'manager', 'cashier', 'mechanic']
    ).annotate(
        completed_orders=Count('service_orders', filter=Q(service_orders__status='completed')),
        in_progress_orders=Count('service_orders', filter=Q(service_orders__status='in-progress'))
    )

    if search_term:
        staff = staff.filter(
            Q(username__icontains=search_term) |
            Q(email__icontains=search_term) |
            Q(role__icontains=search_term) |
            Q(specialization__icontains=search_term)
        )

    staff_data = []
    for user in staff:
        completed_today = user.service_orders.filter(
            status='completed',
            created_date=date.today()
        ).count()
        staff_data.append({
            'id': user.id,
            'name': user.username,
            'email': user.email,
            'phone': user.phone,
            'role': user.role,
            'experience': user.experience_level,
            'specialization': user.specialization,
            'status': user.current_status,
            'current_orders': [so.order_no for so in user.service_orders.filter(status='in-progress')],
            'completed_today': completed_today,
            'completed_total': user.completed_orders,
            'in_progress': user.in_progress_orders,
            'rating': float(user.average_rating or 0.0),
            'join_date': user.date_joined.strftime('%Y-%m-%d'),
            'base_salary': float(user.base_salary or 0.0),
            'previous_dues': float(user.previous_dues or 0.0),
            'profile_image': user.profile_image.url if user.profile_image else None,
        })

    stats = {
        'active_staff': staff.filter(current_status='active').count(),
        'in_progress': sum(s['in_progress'] for s in staff_data),
        'completed_today': sum(s['completed_today'] for s in staff_data),
        'avg_rating': float(staff.aggregate(avg_rating=Avg('average_rating'))['avg_rating'] or 0.0),
        'low_performance': [s['name'] for s in staff_data if s['rating'] < 4.3 or (s['completed_total'] + s['in_progress'] > 0 and (s['completed_total'] / (s['completed_total'] + s['in_progress'])) < 0.5)],
    }

    return JsonResponse({'staff': staff_data, 'stats': stats}, status=200)

@login_required
def save_staff(request):
    if request.user.is_superuser or request.user.role != 'admin':
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    if request.method == 'POST':
        try:
            client_garage = request.user.client_garage
            if not client_garage:
                return JsonResponse({'error': 'No client garage associated'}, status=400)

            user_id = request.POST.get('id')
            username = request.POST.get('name')
            email = request.POST.get('email')
            phone = request.POST.get('phone')
            role = request.POST.get('role')
            password = request.POST.get('password')
            experience_level = request.POST.get('experience')
            specialization = request.POST.get('specialization')
            join_date = request.POST.get('join_date')
            base_salary = request.POST.get('base_salary')
            previous_dues = request.POST.get('previous_dues')
            current_status = request.POST.get('status')
            profile_image = request.FILES.get('profile_image')

            if not all([username, email, role]):
                return JsonResponse({'error': 'Name, email, and role are required'}, status=400)
            if not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', email):
                return JsonResponse({'error': 'Invalid email format'}, status=400)
            if role not in ['staff', 'manager', 'cashier', 'mechanic']:
                return JsonResponse({'error': 'Invalid role'}, status=400)
            if phone and not re.match(r'^\+?[\d\s-]{10,}$', phone):
                return JsonResponse({'error': 'Invalid phone number format'}, status=400)
            if password and len(password) < 8:
                return JsonResponse({'error': 'Password must be at least 8 characters long'}, status=400)
            if base_salary and float(base_salary) < 0:
                return JsonResponse({'error': 'Base salary cannot be negative'}, status=400)
            if previous_dues and float(previous_dues) < 0:
                return JsonResponse({'error': 'Previous dues cannot be negative'}, status=400)

            active_financial_year = FinancialYear.objects.filter(status='active').first()
            active_client_fiscal_year = ClientFiscalYear.objects.filter(client_garage=client_garage, status='active').first()
            
            if user_id:
                user = User.objects.get(pk=user_id, client_garage=client_garage)
                if User.objects.filter(email=email, client_garage=client_garage).exclude(pk=user_id).exists():
                    return JsonResponse({'error': 'Email already exists'}, status=400)
                user.username = username
                user.email = email
                user.phone = phone
                user.role = role
                user.experience_level = experience_level
                user.specialization = specialization
                user.base_salary = Decimal(base_salary) if base_salary else None
                user.previous_dues = Decimal(previous_dues) if previous_dues else None
                user.current_status = current_status
                if join_date:
                    user.date_joined = datetime.strptime(join_date, '%Y-%m-%d')
                if password:
                    user.set_password(password)
                    user.plaintext_password = password
                if profile_image:
                    if user.profile_image and os.path.isfile(user.profile_image.path):
                        os.remove(user.profile_image.path)
                    user.profile_image = profile_image
                user.save()
            else:
                if not active_client_fiscal_year or not active_financial_year:
                    return JsonResponse({'error': 'No active fiscal years found'}, status=400)
                if User.objects.filter(email=email, client_garage=client_garage).exists():
                    return JsonResponse({'error': 'Email already exists'}, status=400)
                if not password:
                    return JsonResponse({'error': 'Password is required for new users'}, status=400)
                user = User.objects.create_user(
                    username=username,
                    email=email,
                    password=password,
                    role='staff',  # Always create with 'staff' role
                    client_garage=client_garage,
                    financial_year=active_financial_year,
                    client_fiscal_year=active_client_fiscal_year,
                    phone=phone,
                    experience_level=experience_level,
                    specialization=specialization,
                    base_salary=Decimal(base_salary) if base_salary else None,
                    previous_dues=Decimal(previous_dues) if previous_dues else None,
                    current_status=current_status,
                    profile_image=profile_image
                )

            return JsonResponse({'message': 'Staff saved successfully'}, status=200)
        except User.DoesNotExist:
            return JsonResponse({'error': 'Staff not found'}, status=404)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid request method'}, status=400)

@login_required
def delete_staff(request):
    if request.user.is_superuser or request.user.role != 'admin':
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    if request.method == 'POST':
        try:
            user_id = request.POST.get('id')
            user = User.objects.get(pk=user_id, client_garage=request.user.client_garage)
            if user.current_status == 'active' and user.service_orders.filter(status__in=['in-progress', 'waiting-assignment']).exists():
                return JsonResponse({'error': 'Cannot delete staff with active service orders'}, status=400)
            user.delete()
            return JsonResponse({'message': 'Staff deleted successfully'}, status=200)
        except User.DoesNotExist:
            return JsonResponse({'error': 'Staff not found'}, status=404)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid request method'}, status=400)

@login_required
def save_payroll(request):
    if request.user.is_superuser or request.user.role != 'admin':
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    if request.method == 'POST':
        try:
            client_garage = request.user.client_garage
            user_id = request.POST.get('user_id')
            amount = request.POST.get('amount')
            payment_mode = request.POST.get('payment_mode')
            notes = request.POST.get('notes')
            incentives = request.POST.get('incentives', 0)

            if not all([user_id, amount, payment_mode]):
                return JsonResponse({'error': 'User ID, amount, and payment mode are required'}, status=400)
            amount = Decimal(amount)
            incentives = Decimal(incentives)
            if amount <= 0:
                return JsonResponse({'error': 'Payment amount must be positive'}, status=400)
            if incentives < 0:
                return JsonResponse({'error': 'Incentives cannot be negative'}, status=400)

            user = User.objects.get(pk=user_id, client_garage=client_garage)
            payroll = StaffPayroll.objects.create(
                user=user,
                client_garage=client_garage,
                amount=amount,
                payment_mode=payment_mode,
                notes=notes,
                incentives=incentives
            )
            user.previous_dues = max(Decimal(0), user.previous_dues - amount)
            user.save()

            return JsonResponse({'message': 'Payroll payment added successfully'}, status=200)
        except User.DoesNotExist:
            return JsonResponse({'error': 'Staff not found'}, status=404)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid request method'}, status=400)

@login_required
def get_payroll(request):
    if request.user.is_superuser or request.user.role != 'admin':
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    try:
        user_id = request.GET.get('user_id')
        user = User.objects.get(pk=user_id, client_garage=request.user.client_garage)
        payrolls = StaffPayroll.objects.filter(user=user).order_by('-payment_date')
        payroll_data = [{
            'id': p.id,
            'date': p.payment_date.strftime('%Y-%m-%d'),
            'amount': float(p.amount),
            'payment_mode': p.payment_mode,
            'notes': p.notes,
            'incentives': float(p.incentives),
        } for p in payrolls]
        return JsonResponse({
            'base_salary': float(user.base_salary or 0.0),
            'previous_dues': float(user.previous_dues or 0.0),
            'incentives': float(payrolls.aggregate(total_incentives=Sum('incentives'))['total_incentives'] or 0.0),
            'payments': payroll_data,
            'total_payable': float((user.base_salary or 0) + (user.previous_dues or 0) + (payrolls.aggregate(total_incentives=Sum('incentives'))['total_incentives'] or 0))
        }, status=200)
    except User.DoesNotExist:
        return JsonResponse({'error': 'Staff not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def generate_payroll_statement(request):
    if request.user.is_superuser or request.user.role != 'admin':
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    if request.method == 'POST':
        try:
            user_ids = json.loads(request.POST.get('user_ids', '[]'))
            month = int(request.POST.get('month'))
            year = int(request.POST.get('year'))
            client_garage = request.user.client_garage

            start_date = date(year, month, 1)
            end_date = (start_date + timedelta(days=31)).replace(day=1) - timedelta(days=1)

            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="payroll_statement_{month}_{year}.csv"'

            writer = csv.writer(response)
            writer.writerow(['Staff Name', 'Email', 'Role', 'Base Salary', 'Incentives', 'Payments', 'Dues', 'Attendance Days'])

            for user_id in user_ids:
                user = User.objects.get(pk=user_id, client_garage=client_garage)
                payrolls = StaffPayroll.objects.filter(
                    user=user,
                    payment_date__range=[start_date, end_date]
                )
                attendance = StaffAttendance.objects.filter(
                    user=user,
                    date__range=[start_date, end_date],
                    status='present'
                ).count()
                total_incentives = payrolls.aggregate(total_incentives=Sum('incentives'))['total_incentives'] or 0
                total_payments = payrolls.aggregate(total_amount=Sum('amount'))['total_amount'] or 0

                writer.writerow([
                    user.username,
                    user.email,
                    user.role,
                    float(user.base_salary or 0),
                    float(total_incentives),
                    float(total_payments),
                    float(user.previous_dues or 0),
                    attendance
                ])

            return response
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid request method'}, status=400)

@login_required
def save_attendance(request):
    if request.user.is_superuser or request.user.role != 'admin':
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    if request.method == 'POST':
        try:
            user_id = request.POST.get('user_id')
            date_str = request.POST.get('date')
            status = request.POST.get('status')
            check_in = request.POST.get('check_in')
            check_out = request.POST.get('check_out')
            notes = request.POST.get('notes')

            if not all([user_id, date_str, status]):
                return JsonResponse({'error': 'User ID, date, and status are required'}, status=400)
            
            attendance_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            user = User.objects.get(pk=user_id, client_garage=request.user.client_garage)

            attendance, created = StaffAttendance.objects.update_or_create(
                user=user,
                date=attendance_date,
                defaults={
                    'client_garage': request.user.client_garage,
                    'status': status,
                    'check_in': datetime.strptime(check_in, '%Y-%m-%dT%H:%M') if check_in else None,
                    'check_out': datetime.strptime(check_out, '%Y-%m-%dT%H:%M') if check_out else None,
                    'notes': notes
                }
            )

            return JsonResponse({'message': 'Attendance saved successfully'}, status=200)
        except User.DoesNotExist:
            return JsonResponse({'error': 'Staff not found'}, status=404)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid request method'}, status=400)

@login_required
def get_attendance(request):
    if request.user.is_superuser or request.user.role != 'admin':
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    try:
        user_id = request.GET.get('user_id')
        month = int(request.GET.get('month'))
        year = int(request.GET.get('year'))
        
        start_date = date(year, month, 1)
        end_date = (start_date + timedelta(days=31)).replace(day=1) - timedelta(days=1)

        user = User.objects.get(pk=user_id, client_garage=request.user.client_garage)
        attendances = StaffAttendance.objects.filter(
            user=user,
            date__range=[start_date, end_date]
        ).order_by('date')

        attendance_data = [{
            'date': a.date.strftime('%Y-%m-%d'),
            'status': a.status,
            'check_in': a.check_in.strftime('%H:%M') if a.check_in else None,
            'check_out': a.check_out.strftime('%H:%M') if a.check_out else None,
            'notes': a.notes
        } for a in attendances]

        return JsonResponse({'attendances': attendance_data}, status=200)
    except User.DoesNotExist:
        return JsonResponse({'error': 'Staff not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)