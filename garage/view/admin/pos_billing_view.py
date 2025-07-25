from django.shortcuts import redirect, render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
from garage.models import ClientGarage, Customer, ServiceOrderItem, Vehicle, Bill, BillItem, ServiceOrder, Part, PartCategory, ServiceType
import json
import logging
from django.db.models import Q
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
import io
import uuid

logger = logging.getLogger(__name__)

@login_required
def get_items(request):
    try:
        client_garage = ClientGarage.objects.get(user=request.user)
        search_query = request.GET.get('q', '')
        
        # Fetch parts
        parts = Part.objects.filter(client_garage=client_garage)
        if search_query:
            parts = parts.filter(
                Q(name__icontains=search_query) | Q(code__icontains=search_query)
            )
        
        # Fetch services
        services = ServiceType.objects.filter(client_garage=client_garage)
        if search_query:
            services = services.filter(
                Q(name__icontains=search_query)
            )
        
        # Combine results
        results = [
            {
                'id': part.id,
                'code': part.code,
                'name': part.name,
                'price': float(part.selling_price),
                'category': part.category.name if part.category else 'Uncategorized',
                'inStock': part.in_stock,
                'image': 'fa-cogs',
                'isService': False
            }
            for part in parts
        ] + [
            {
                'id': f"service-{service.id}",
                'code': f"SVC-{service.id}",
                'name': service.name,
                'price': float(service.base_price),
                'category': 'Service',
                'inStock': 9999,  # Services don't have stock limits
                'image': 'fa-tools',
                'isService': True
            }
            for service in services
        ]
        
        logger.info(f"Fetched {len(results)} items (parts and services) for user {request.user.username}")
        return JsonResponse({'items': results})
    except ClientGarage.DoesNotExist:
        logger.error(f"No ClientGarage found for user {request.user.username}")
        return JsonResponse({'status': 'error', 'message': 'Client garage not found'}, status=404)
    except Exception as e:
        logger.error(f"Error in get_items for user {request.user.username}: {str(e)}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

# Other views remain unchanged
@login_required
def pos_billing(request):
    if request.user.is_superuser or request.user.role != 'admin':
        logger.info(f"Redirecting user {request.user.username} with role {request.user.role} to {request.user.role}/dashboard/")
        return redirect(f'/{request.user.role}/dashboard/')
    
    try:
        client_garage = ClientGarage.objects.get(user=request.user)
        initial_data = {}
        bill_id = request.GET.get('bill_id')
        vehicle_id = request.GET.get('vehicle_id')
        order_no = request.GET.get('orderNo')
        services = request.GET.get('services')
        total = request.GET.get('total')
        customer_name = request.GET.get('customer')
        vehicle_number = request.GET.get('vehicle')
        
        if bill_id:
            bill = get_object_or_404(Bill, id=bill_id, client_garage=client_garage)
            initial_data = {
                'bill_id': bill.id,
                'bill_no': bill.bill_no,
                'order_no': bill.order_no if hasattr(bill, 'order_no') else None,
                'customer': {
                    'id': bill.customer.id if bill.customer else None,
                    'name': bill.customer.name if bill.customer else 'Anonymous',
                    'phone': bill.customer.phone if bill.customer else ''
                },
                'vehicle': {
                    'id': bill.vehicle.id if bill.vehicle else None,
                    'vehicle_number': bill.vehicle.vehicle_number if bill.vehicle else ''
                },
                'items': [
                    {
                        'id': f"service-{bi.service_type.id}" if bi.service_type else bi.item.id if bi.item else f"service-{uuid.uuid4().hex[:8]}",
                        'name': bi.name,
                        'price': float(bi.price),
                        'quantity': bi.quantity,
                        'image': 'fa-tools' if bi.service_type else 'fa-cogs',
                        'isService': bi.service_type is not None
                    }
                    for bi in bill.bill_items.all()
                ],
                'total': float(bill.total),
                'discount_type': bill.discount_type,
                'discount_value': float(bill.discount_value),
                'tax': float(bill.tax),
                'credit_amount': float(bill.credit_amount),
                'payment_mode': bill.payment_mode,
                'status': bill.status
            }
        elif order_no and services:
            try:
                services_list = json.loads(services)
                customer = None
                vehicle = None
                if customer_name and customer_name != 'Anonymous':
                    customer, _ = Customer.objects.get_or_create(
                        client_garage=client_garage,
                        name=customer_name,
                        defaults={'phone': ''}
                    )
                if vehicle_number:
                    vehicle = Vehicle.objects.filter(client_garage=client_garage, vehicle_number=vehicle_number).first()
                    if vehicle and customer and vehicle.customer != customer:
                        vehicle.customer = customer
                        vehicle.save()
                
                initial_data = {
                    'bill_id': None,
                    'bill_no': None,
                    'order_no': order_no,
                    'customer': {
                        'id': customer.id if customer else None,
                        'name': customer_name or 'Anonymous',
                        'phone': customer.phone if customer else ''
                    },
                    'vehicle': {
                        'id': vehicle.id if vehicle else None,
                        'vehicle_number': vehicle_number or ''
                    },
                    'items': [
                        {
                            'id': f"service-{uuid.uuid4().hex[:8]}",
                            'name': service['name'],
                            'price': float(service['price']),
                            'quantity': 1,
                            'image': 'fa-tools',
                            'isService': True
                        }
                        for service in services_list
                    ],
                    'total': float(total) if total else sum(float(s['price']) for s in services_list),
                    'discount_type': 'percentage',
                    'discount_value': 0.0,
                    'tax': 0.0,
                    'credit_amount': 0.0,
                    'payment_mode': 'cash',
                    'status': 'Pending'
                }
            except json.JSONDecodeError:
                logger.error(f"Invalid services JSON for order {order_no}: {services}")
                return JsonResponse({'status': 'error', 'message': 'Invalid services data'}, status=400)
        
        logger.info(f"Rendering pos_billing.html for user {request.user.username} with initial_data: {initial_data}")
        return render(request, 'admin/pos_billing.html', {
            'user': request.user,
            'initial_data': json.dumps(initial_data),
            'client_garage': {
                'name': client_garage.name,
                'address': client_garage.address or 'Kathmandu, Nepal',
                'contact': client_garage.contact or '+9779702800835',
                'email': client_garage.email or '',
                'logo': client_garage.logo.url if client_garage.logo else ''
            }
        })
    except ClientGarage.DoesNotExist:
        logger.error(f"No ClientGarage found for user {request.user.username}")
        return JsonResponse({'status': 'error', 'message': 'Client garage not found'}, status=404)
    except Exception as e:
        logger.error(f"Error in pos_billing for user {request.user.username}: {str(e)}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@login_required
def get_item(request):
    try:
        client_garage = ClientGarage.objects.get(user=request.user)
        item_id = request.GET.get('item_id')
        is_service = item_id.startswith('service-')
        if is_service:
            service_id = item_id.replace('service-', '')
            service = get_object_or_404(ServiceType, id=service_id, client_garage=client_garage)
            result = {
                'id': f"service-{service.id}",
                'name': service.name,
                'price': float(service.base_price),
                'image': 'fa-tools',
                'isService': True
            }
        else:
            part = get_object_or_404(Part, id=item_id, client_garage=client_garage)
            result = {
                'id': part.id,
                'name': part.name,
                'price': float(part.selling_price),
                'image': 'fa-cogs',
                'isService': False
            }
        logger.info(f"Fetched item {result['name']} (ID: {item_id}) for user {request.user.username}")
        return JsonResponse(result)
    except ClientGarage.DoesNotExist:
        logger.error(f"No ClientGarage found for user {request.user.username}")
        return JsonResponse({'status': 'error', 'message': 'Client garage not found'}, status=404)
    except Exception as e:
        logger.error(f"Error in get_item for user {request.user.username}: {str(e)}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@login_required
def get_bills(request):
    try:
        client_garage = ClientGarage.objects.get(user=request.user)
        status_filter = request.GET.get('status', 'all')
        search_query = request.GET.get('q', '')
        page = int(request.GET.get('page', 1))
        items_per_page = 10
        
        bills = Bill.objects.filter(client_garage=client_garage).order_by('-created_at')
        
        if status_filter != 'all':
            statuses = status_filter.split(',')
            normalized_statuses = [s if s != 'in-progress' else 'Generated (In Progress)' for s in statuses]
            bills = bills.filter(Q(status__in=normalized_statuses))
        
        if search_query:
            bills = bills.filter(
                Q(bill_no__icontains=search_query) |
                Q(customer__name__icontains=search_query) |
                Q(vehicle__vehicle_number__icontains=search_query) |
                Q(service_order__order_no__icontains=search_query)
            )
        
        total = bills.count()
        start = (page - 1) * items_per_page
        end = start + items_per_page
        paginated_bills = bills[start:end]
        
        results = []
        for bill in paginated_bills:
            bill_items = [
                {
                    'id': f"service-{bi.service_type.id}" if bi.service_type else bi.item.id if bi.item else f"temp-{uuid.uuid4().hex[:8]}",
                    'name': bi.name,
                    'price': float(bi.price),
                    'quantity': bi.quantity,
                    'isService': bi.service_type is not None
                }
                for bi in bill.bill_items.all()
            ]
            # Add ServiceOrderItems if service_order exists
            if bill.service_order:
                service_order_items = ServiceOrderItem.objects.filter(service_order=bill.service_order)
                for service_item in service_order_items:
                    if not any(item['id'] == f"service-{service_item.service_type.id}" for item in bill_items):
                        bill_items.append({
                            'id': f"service-{service_item.service_type.id}",
                            'name': service_item.service_type.name,
                            'price': float(service_item.price),
                            'quantity': 1,
                            'isService': True
                        })
            
            results.append({
                'id': bill.id,
                'bill_no': bill.bill_no,
                'customer_id': bill.customer.id if bill.customer else None,
                'customer_name': bill.customer.name if bill.customer else 'Anonymous',
                'customer_phone': bill.customer.phone if bill.customer else '',
                'vehicle_id': bill.vehicle.id if bill.vehicle else None,
                'vehicle_number': bill.vehicle.vehicle_number if bill.vehicle else 'N/A',
                'order_no': bill.service_order.order_no if bill.service_order else None,
                'total': float(bill.total),
                'status': 'in-progress' if bill.status == 'Generated (In Progress)' else bill.status.lower(),
                'date': bill.created_at.strftime('%Y-%m-%d'),
                'items': bill_items
            })
        
        logger.info(f"Fetched {len(results)} bills for user {request.user.username}, page {page}")
        return JsonResponse({
            'bills': results,
            'total': total,
            'page': page,
            'items_per_page': items_per_page
        })
    except Exception as e:
        logger.error(f"Error in get_bills for user {request.user.username}: {str(e)}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    

@login_required
@require_POST
def save_customer(request):
    try:
        data = json.loads(request.body)
        client_garage = ClientGarage.objects.get(user=request.user)
        name = data.get('name', 'Anonymous').strip()
        phone = data.get('phone', '').strip()
        vehicle_number = data.get('vehicle', '').strip()
        
        customer = None
        if name != 'Anonymous' or phone:
            customer, _ = Customer.objects.get_or_create(
                client_garage=client_garage,
                phone=phone if phone else None,
                defaults={'name': name}
            )
            if not _ and (customer.name != name or customer.phone != phone):
                customer.name = name
                customer.phone = phone if phone else None
                customer.save()
        
        vehicle = None
        if vehicle_number:
            vehicle = Vehicle.objects.filter(client_garage=client_garage, vehicle_number=vehicle_number).first()
            if vehicle and customer and vehicle.customer != customer:
                vehicle.customer = customer
                vehicle.save()
        
        result = {
            'id': customer.id if customer else None,
            'name': customer.name if customer else 'Anonymous',
            'phone': customer.phone if customer else '',
            'vehicle': vehicle.vehicle_number if vehicle else '',
            'vehicle_id': vehicle.id if vehicle else None
        }
        logger.info(f"Saved customer {name} for user {request.user.username}")
        return JsonResponse({'status': 'success', 'customer': result})
    except ClientGarage.DoesNotExist:
        logger.error(f"No ClientGarage found for user {request.user.username}")
        return JsonResponse({'status': 'error', 'message': 'Client garage not found'}, status=404)
    except Exception as e:
        logger.error(f"Error in save_customer for user {request.user.username}: {str(e)}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@login_required
@require_POST
def save_bill(request):
    try:
        client_garage = ClientGarage.objects.get(user=request.user)
        data = json.loads(request.body)
        bill_id = data.get('bill_id')
        customer_id = data.get('customer_id')
        vehicle_id = data.get('vehicle_id')
        items = data.get('items', [])
        total = data.get('total')
        status = data.get('status', 'Pending')
        discount = data.get('discount', {'type': 'percentage', 'value': 0})
        credit = data.get('credit', 0)
        payment_mode = data.get('payment_mode', 'cash')
        order_no = data.get('order_no')

        customer = Customer.objects.filter(id=customer_id, client_garage=client_garage).first() if customer_id else None
        vehicle = Vehicle.objects.filter(id=vehicle_id, client_garage=client_garage).first() if vehicle_id else None
        service_order = ServiceOrder.objects.filter(order_no=order_no, client_garage=client_garage).first() if order_no else None

        bill = Bill.objects.get(id=bill_id, client_garage=client_garage) if bill_id else Bill(
            client_garage=client_garage,
            bill_no=f'B{timezone.now().strftime("%Y%m%d%H%M%S")}',
            customer=customer,
            vehicle=vehicle,
            service_order=service_order
        )

        # Fetch service charges from ServiceOrderItem if service_order exists
        if service_order:
            service_order_items = ServiceOrderItem.objects.filter(service_order=service_order)
            for service_item in service_order_items:
                if not any(item.get('id') == f"service-{service_item.service_type.id}" for item in items):
                    items.append({
                        'id': f"service-{service_item.service_type.id}",
                        'name': service_item.service_type.name,
                        'price': float(service_item.price),
                        'quantity': 1,
                        'isService': True
                    })

        bill.total = total
        bill.discount_type = discount['type']
        bill.discount_value = discount['value']
        bill.tax = (total - (total * discount['value'] / 100 if discount['type'] == 'percentage' else discount['value'])) * 0.13
        bill.credit_amount = credit
        bill.payment_mode = payment_mode
        bill.status = status
        bill.save()

        bill.bill_items.all().delete()
        for item in items:
            part = None
            service_type = None
            if item.get('isService', False):
                service_id = item['id'].replace('service-', '') if item.get('id') else None
                if service_id:
                    service_type = ServiceType.objects.filter(id=service_id, client_garage=client_garage).first()
                if not service_type:
                    service_type = ServiceType.objects.create(
                        client_garage=client_garage,
                        name=item['name'],
                        category='Temporary',
                        base_price=item['price']
                    )
            else:
                part = Part.objects.filter(id=item['id'], client_garage=client_garage).first() if item.get('id') else None
                if not part:
                    continue
            BillItem.objects.create(
                bill=bill,
                item=part,
                service_type=service_type,
                name=item['name'],
                price=item['price'],
                quantity=item['quantity']
            )

        bill.items = [
            {
                'id': f"service-{bi.service_type.id}" if bi.service_type else bi.item.id if bi.item else f"temp-{uuid.uuid4().hex[:8]}",
                'name': bi.name,
                'price': float(bi.price),
                'quantity': bi.quantity,
                'isService': bi.service_type is not None
            }
            for bi in bill.bill_items.all()
        ]
        bill.save()

        return JsonResponse({'status': 'success', 'bill_id': bill.id})
    except Exception as e:
        logger.error(f"Error saving bill for user {request.user.username}: {str(e)}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    
@login_required
@require_POST
def generate_bill(request):
    try:
        client_garage = ClientGarage.objects.get(user=request.user)
        data = json.loads(request.body)
        bill_id = data.get('bill_id')
        customer_id = data.get('customer_id')
        vehicle_id = data.get('vehicle_id')
        items = data.get('items', [])
        total = data.get('total')
        status = data.get('status', 'Completed')
        discount = data.get('discount', {'type': 'percentage', 'value': 0})
        credit = data.get('credit', 0)
        payment_mode = data.get('payment_mode', 'cash')
        order_no = data.get('order_no')

        customer = Customer.objects.filter(id=customer_id, client_garage=client_garage).first() if customer_id else None
        vehicle = Vehicle.objects.filter(id=vehicle_id, client_garage=client_garage).first() if vehicle_id else None
        service_order = ServiceOrder.objects.filter(order_no=order_no, client_garage=client_garage).first() if order_no else None

        bill = Bill.objects.get(id=bill_id, client_garage=client_garage) if bill_id else Bill(
            client_garage=client_garage,
            bill_no=f'B{timezone.now().strftime("%Y%m%d%H%M%S")}',
            customer=customer,
            vehicle=vehicle,
            service_order=service_order
        )

        # Fetch service charges from ServiceOrderItem if service_order exists
        if service_order:
            service_order_items = ServiceOrderItem.objects.filter(service_order=service_order)
            for service_item in service_order_items:
                # Avoid duplicating items if already in the items list
                if not any(item.get('id') == f"service-{service_item.service_type.id}" for item in items):
                    items.append({
                        'id': f"service-{service_item.service_type.id}",
                        'name': service_item.service_type.name,
                        'price': float(service_item.price),
                        'quantity': 1,
                        'isService': True
                    })

        # Calculate tax
        subtotal = sum(item['price'] * item['quantity'] for item in items)
        discount_amount = (subtotal * discount['value'] / 100) if discount['type'] == 'percentage' else discount['value']
        tax = (subtotal - discount_amount) * 0.13

        # Update bill fields
        bill.total = total
        bill.discount_type = discount['type']
        bill.discount_value = discount['value']
        bill.tax = tax
        bill.credit_amount = credit
        bill.payment_mode = payment_mode
        bill.status = status
        bill.save()

        # NEW: Update ServiceOrder status to "completed" if bill is "Completed"
        if service_order and status == 'Completed':
            service_order.status = 'completed'
            service_order.updated_at = timezone.now()
            service_order.save()
            # NEW: Release mechanics by deleting their assignments
            service_order.mechanics.clear()  # Removes all mechanic assignments from garage_serviceorder_mechanics

        # Clear existing bill items
        bill.bill_items.all().delete()

        # Save bill items
        for item in items:
            part = None
            service_type = None
            if item.get('isService', False):
                service_id = item['id'].replace('service-', '') if item.get('id') else None
                if service_id:
                    service_type = ServiceType.objects.filter(id=service_id, client_garage=client_garage).first()
                if not service_type:
                    # Fallback: Create a temporary ServiceType if not found
                    service_type = ServiceType.objects.create(
                        client_garage=client_garage,
                        name=item['name'],
                        category='Temporary',
                        base_price=item['price']
                    )
            else:
                part = Part.objects.filter(id=item['id'], client_garage=client_garage).first() if item.get('id') else None
                if not part:
                    continue  # Skip invalid parts
            BillItem.objects.create(
                bill=bill,
                item=part,
                service_type=service_type,
                name=item['name'],
                price=item['price'],
                quantity=item['quantity']
            )

        # Update JSONField for compatibility
        bill.items = [
            {
                'id': f"service-{bi.service_type.id}" if bi.service_type else bi.item.id if bi.item else f"temp-{uuid.uuid4().hex[:8]}",
                'name': bi.name,
                'price': float(bi.price),
                'quantity': bi.quantity,
                'isService': bi.service_type is not None
            }
            for bi in bill.bill_items.all()
        ]
        bill.save()

        return JsonResponse({
            'status': 'success',
            'bill': {
                'id': bill.id,
                'bill_no': bill.bill_no,
                'order_no': bill.service_order.order_no if bill.service_order else None,
                'customer_id': bill.customer.id if bill.customer else None,
                'customer_name': bill.customer.name if bill.customer else 'Anonymous',
                'customer_phone': bill.customer.phone if bill.customer else '',
                'vehicle_id': bill.vehicle.id if bill.vehicle else None,
                'vehicle_number': bill.vehicle.vehicle_number if bill.vehicle else '',
                'items': bill.items,
                'total': float(bill.total),
                'discount_type': bill.discount_type,
                'discount_value': float(bill.discount_value),
                'tax': float(bill.tax),
                'credit_amount': float(bill.credit_amount),
                'payment_mode': bill.payment_mode,
                'date': bill.created_at.strftime('%Y-%m-%d')
            }
        })
    except Exception as e:
        logger.error(f"Error generating bill for user {request.user.username}: {str(e)}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    

@login_required
def get_bill(request):
    try:
        bill_id = request.GET.get('bill_id')
        bill = Bill.objects.get(id=bill_id, client_garage__user=request.user)
        bill_items = [
            {
                'id': f"service-{bi.service_type.id}" if bi.service_type else bi.item.id if bi.item else f"temp-{uuid.uuid4().hex[:8]}",
                'name': bi.name,
                'price': float(bi.price),
                'quantity': bi.quantity,
                'isService': bi.service_type is not None,
                'image': 'fa-tools' if bi.service_type else 'fa-cogs'
            }
            for bi in bill.bill_items.all()
        ]
        # Add ServiceOrderItems if service_order exists
        if bill.service_order:
            service_order_items = ServiceOrderItem.objects.filter(service_order=bill.service_order)
            for service_item in service_order_items:
                if not any(item['id'] == f"service-{service_item.service_type.id}" for item in bill_items):
                    bill_items.append({
                        'id': f"service-{service_item.service_type.id}",
                        'name': service_item.service_type.name,
                        'price': float(service_item.price),
                        'quantity': 1,
                        'isService': True,
                        'image': 'fa-tools'
                    })

        return JsonResponse({
            'id': bill.id,
            'bill_no': bill.bill_no,
            'order_no': bill.service_order.order_no if bill.service_order else None,
            'customer_id': bill.customer.id if bill.customer else None,
            'customer_name': bill.customer.name if bill.customer else 'Anonymous',
            'customer_phone': bill.customer.phone if bill.customer else '',
            'vehicle_id': bill.vehicle.id if bill.vehicle else None,
            'vehicle_number': bill.vehicle.vehicle_number if bill.vehicle else '',
            'items': bill_items,
            'total': float(bill.total),
            'discount_type': bill.discount_type,
            'discount_value': float(bill.discount_value),
            'tax': float(bill.tax),
            'credit_amount': float(bill.credit_amount),
            'payment_mode': bill.payment_mode,
            'date': bill.created_at.strftime('%Y-%m-%d')
        })
    except Bill.DoesNotExist:
        logger.error(f"Bill {bill_id} not found for user {request.user.username}")
        return JsonResponse({'status': 'error', 'message': 'Bill not found'}, status=404)
    except Exception as e:
        logger.error(f"Error fetching bill {bill_id} for user {request.user.username}: {str(e)}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@login_required
@require_POST
def delete_bill(request):
    try:
        data = json.loads(request.body)
        bill_id = data.get('bill_id')
        client_garage = ClientGarage.objects.get(user=request.user)
        bill = get_object_or_404(Bill, id=bill_id, client_garage=client_garage)
        
        # Restore stock for parts only
        for bill_item in bill.bill_items.all():
            if bill_item.item:  # Only restore stock for parts
                part = bill_item.item
                part.in_stock += bill_item.quantity
                part.updated_at = timezone.now()
                part.save()
        
        bill.delete()
        logger.info(f"Deleted bill {bill.bill_no} for user {request.user.username}")
        return JsonResponse({'status': 'success', 'message': 'Bill deleted successfully'})
    except ClientGarage.DoesNotExist:
        logger.error(f"No ClientGarage found for user {request.user.username}")
        return JsonResponse({'status': 'error', 'message': 'Client garage not found'}, status=404)
    except Exception as e:
        logger.error(f"Error in delete_bill for user {request.user.username}: {str(e)}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@login_required
def generate_bill_pdf(request):
    try:
        bill_id = request.GET.get('bill_id')
        client_garage = ClientGarage.objects.get(user=request.user)
        bill = get_object_or_404(Bill, id=bill_id, client_garage=client_garage)
        
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        elements = []
        styles = getSampleStyleSheet()
        
        title_style = ParagraphStyle(name='Title', fontSize=16, leading=20, alignment=1, spaceAfter=12)
        normal_style = ParagraphStyle(name='Normal', fontSize=10, leading=12)
        bold_style = ParagraphStyle(name='Bold', fontSize=10, leading=12, fontName='Helvetica-Bold')
        
        elements.append(Paragraph(client_garage.name, title_style))
        elements.append(Paragraph(client_garage.address or 'Kathmandu, Nepal', normal_style))
        if client_garage.contact:
            elements.append(Paragraph(f"Contact: {client_garage.contact}", normal_style))
        if client_garage.email:
            elements.append(Paragraph(f"Email: {client_garage.email}", normal_style))
        elements.append(Spacer(1, 0.2 * inch))
        
        elements.append(Paragraph(f"Bill No: {bill.bill_no}", normal_style))
        elements.append(Paragraph(f"Date: {bill.created_at.strftime('%Y-%m-%d')}", normal_style))
        elements.append(Spacer(1, 0.2 * inch))
        
        elements.append(Paragraph("Customer Details", bold_style))
        elements.append(Paragraph(bill.customer.name if bill.customer else 'Anonymous', normal_style))
        if bill.customer and bill.customer.phone:
            elements.append(Paragraph(bill.customer.phone, normal_style))
        if bill.vehicle and bill.vehicle.vehicle_number:
            elements.append(Paragraph(bill.vehicle.vehicle_number, normal_style))
        elements.append(Spacer(1, 0.2 * inch))
        
        data = [['Item', 'Qty', 'Price', 'Total']]
        for bi in bill.bill_items.all():
            data.append([
                bi.name,
                str(bi.quantity),
                f"NPR {bi.price:.2f}",
                f"NPR {(bi.price * bi.quantity):.2f}"
            ])
        table = Table(data)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        elements.append(table)
        elements.append(Spacer(1, 0.2 * inch))
        
        subtotal = sum(bi.price * bi.quantity for bi in bill.bill_items.all())
        elements.append(Paragraph(f"Subtotal: NPR {subtotal:.2f}", normal_style))
        elements.append(Paragraph(f"Discount ({bill.discount_type}): NPR {bill.discount_value:.2f}", normal_style))
        elements.append(Paragraph(f"VAT (13%): NPR {bill.tax:.2f}", normal_style))
        if bill.credit_amount > 0:
            elements.append(Paragraph(f"Credit: NPR {bill.credit_amount:.2f}", normal_style))
        elements.append(Paragraph(f"Total: NPR {bill.total:.2f}", bold_style))
        elements.append(Paragraph(f"Payment Mode: {bill.payment_mode.upper()}", normal_style))
        
        doc.build(elements)
        pdf = buffer.getvalue()
        buffer.close()
        
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="bill_{bill.bill_no}.pdf"'
        response.write(pdf)
        return response
    except ClientGarage.DoesNotExist:
        logger.error(f"No ClientGarage found for user {request.user.username}")
        return JsonResponse({'status': 'error', 'message': 'Client garage not found'}, status=404)
    except Exception as e:
        logger.error(f"Error in generate_bill_pdf for user {request.user.username}: {str(e)}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)