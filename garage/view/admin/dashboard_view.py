from django.shortcuts import redirect, render
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from datetime import timedelta
from garage.models import Vehicle, ServiceOrder, Bill, Part, User, ClientGarage, ClientFiscalYear
from django.db.models import Sum, Count
from django.db import models

@login_required
def dashboard_view(request):
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