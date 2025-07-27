from django.shortcuts import redirect, render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
from garage.models import ClientGarage, Customer, ServiceOrderItem, TaxSetting, Vehicle, Bill, BillItem, ServiceOrder, Part, PartCategory, ServiceType
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
        
        parts = Part.objects.filter(client_garage=client_garage)
        if search_query:
            parts = parts.filter(Q(name__icontains=search_query) | Q(code__icontains=search_query))
        
        services = ServiceType.objects.filter(client_garage=client_garage)
        if search_query:
            services = services.filter(Q(name__icontains=search_query))
        
        results = [
            {
                'id': part.id,
                'code': part.code,
                'name': part.name,
                'price': float(part.selling_price),
                'category': part.category.name if part.category else 'Uncategorized',
                'inStock': part.in_stock,
                'image': part.image.url if part.image else None,  # Include image URL or None
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
                'inStock': 9999,
                'image': None,  # Services have no image
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
                'image': None,  # Services have no image
                'isService': True
            }
        else:
            part = get_object_or_404(Part, id=item_id, client_garage=client_garage)
            result = {
                'id': part.id,
                'name': part.name,
                'price': float(part.selling_price),
                'image': part.image.url if part.image else None,  # Include image URL or None
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

        # Create or update bill
        if bill_id:
            bill = Bill.objects.get(id=bill_id, client_garage=client_garage)
        else:
            # Generate bill number (e.g., B01, B02) to match generate_bill format
            last_bill = Bill.objects.filter(client_garage=client_garage).order_by('-id').first()
            bill_no = f"B{str(last_bill.id + 1 if last_bill else 1).zfill(2)}"
            bill = Bill(
                client_garage=client_garage,
                bill_no=bill_no,
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
    
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.utils import timezone
from garage.models import ClientGarage, Customer, Vehicle, ServiceOrder, ServiceOrderItem, ServiceType, Part, Bill, BillItem, TaxSetting
import json
import logging
import uuid

logger = logging.getLogger(__name__)

@login_required
@require_POST
def generate_bill(request):
    try:
        client_garage = ClientGarage.objects.get(user=request.user)
        data = json.loads(request.body)
        
        # Extract and validate input data
        bill_id = data.get('bill_id')
        customer_id = data.get('customer_id')
        vehicle_id = data.get('vehicle_id')
        items = data.get('items', [])
        total = data.get('total', 0.0)
        status = data.get('status', 'Completed')
        discount = data.get('discount', {'type': 'percentage', 'value': 0})
        credit = data.get('credit', 0)
        payment_mode = data.get('payment_mode', 'cash')
        order_no = data.get('order_no')

        # Validate required fields
        if not items or not isinstance(total, (int, float)) or total < 0:
            logger.error(f"Invalid input: items={items}, total={total}")
            return JsonResponse({'status': 'error', 'message': 'Items and valid total are required'}, status=400)

        # Fetch related objects with validation
        customer = Customer.objects.filter(id=customer_id, client_garage=client_garage).first() if customer_id else None
        vehicle = Vehicle.objects.filter(id=vehicle_id, client_garage=client_garage).first() if vehicle_id else None
        service_order = ServiceOrder.objects.filter(order_no=order_no, client_garage=client_garage).first() if order_no else None

        # Generate bill number (e.g., B01, B02)
        last_bill = Bill.objects.filter(client_garage=client_garage).order_by('-id').first()
        bill_no = f"B{str(last_bill.id + 1 if last_bill else 1).zfill(2)}"  # e.g., B01, B02

        # Create or update bill
        bill = Bill.objects.get(id=bill_id, client_garage=client_garage) if bill_id else Bill(
            client_garage=client_garage,
            bill_no=bill_no,
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

        # Calculate subtotal, discount, and tax
        subtotal = sum(float(item['price']) * int(item['quantity']) for item in items)
        discount_amount = (subtotal * float(discount['value']) / 100) if discount['type'] == 'percentage' else float(discount['value'])
        tax_setting = TaxSetting.objects.filter(client_garage=client_garage).first()
        tax_rate = float(tax_setting.tax_rate) if tax_setting else 13.0
        tax = (subtotal - discount_amount) * (tax_rate / 100)

        # Validate total matches calculated total
        expected_total = subtotal - discount_amount + tax
        if abs(float(total) - expected_total) > 0.01:
            logger.warning(f"Total mismatch: provided={total}, calculated={expected_total}")
            total = expected_total  # Use calculated total for consistency

        # Update bill fields
        bill.total = total
        bill.discount_type = discount['type']
        bill.discount_value = float(discount['value'])
        bill.tax = tax
        bill.credit_amount = float(credit)
        bill.payment_mode = payment_mode
        bill.status = status
        bill.save()

        # Update ServiceOrder status and clear mechanics if completed
        if service_order and status == 'Completed':
            service_order.status = 'completed'
            service_order.updated_at = timezone.now()
            service_order.mechanics.clear()  # Release mechanics
            service_order.save()

        # Clear existing bill items
        bill.bill_items.all().delete()

        # Save bill items
        for item in items:
            if not item.get('name') or not isinstance(item.get('price'), (int, float)) or not isinstance(item.get('quantity'), int):
                logger.warning(f"Skipping invalid item: {item}")
                continue
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
                        base_price=float(item['price'])
                    )
            else:
                part = Part.objects.filter(id=item['id'], client_garage=client_garage).first() if item.get('id') else None
                if not part:
                    logger.warning(f"Part not found for item ID {item.get('id')}")
                    continue
                # Update part stock
                part.in_stock -= item['quantity']
                if part.in_stock < 0:
                    logger.error(f"Insufficient stock for part {part.name} (ID: {part.id})")
                    return JsonResponse({'status': 'error', 'message': f'Insufficient stock for part {part.name}'}, status=400)
                part.save()
            BillItem.objects.create(
                bill=bill,
                item=part,
                service_type=service_type,
                name=item['name'],
                price=float(item['price']),
                quantity=int(item['quantity'])
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

        logger.info(f"Generated bill {bill.bill_no} for user {request.user.username}")
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
    except ClientGarage.DoesNotExist:
        logger.error(f"No ClientGarage found for user {request.user.username}")
        return JsonResponse({'status': 'error', 'message': 'Client garage not found'}, status=404)
    except json.JSONDecodeError:
        logger.error(f"Invalid JSON in generate_bill request for user {request.user.username}")
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON data'}, status=400)
    except Exception as e:
        logger.error(f"Error generating bill for user {request.user.username}: {str(e)}")
        return JsonResponse({'status': 'error', 'message': f'Failed to generate bill: {str(e)}'}, status=500)

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
        if not bill_id or not bill_id.isdigit():
            return JsonResponse({'status': 'error', 'message': 'Invalid bill ID'}, status=400)
        
        client_garage = ClientGarage.objects.get(user=request.user)
        bill = get_object_or_404(Bill, id=bill_id, client_garage=client_garage)
        
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch, leftMargin=0.5*inch, rightMargin=0.5*inch)
        elements = []
        
        # --- Define custom styles for a clean, attractive look ---
        styles = getSampleStyleSheet()
        
        # Custom Colors
        header_bg_color = colors.HexColor('#F0F0F0')
        table_header_bg = colors.HexColor('#212529')
        table_header_text = colors.white
        
        # FIX: Ensure all custom styles are defined here before use
        header_style = ParagraphStyle(name='HeaderStyle', fontSize=18, fontName='Helvetica-Bold', alignment=1, spaceAfter=6, textColor=colors.HexColor('#333333'))
        subheader_style = ParagraphStyle(name='SubheaderStyle', fontSize=10, fontName='Helvetica', alignment=1, spaceAfter=4, textColor=colors.HexColor('#666666'))
        details_label_style = ParagraphStyle(name='DetailsLabelStyle', fontSize=9, fontName='Helvetica-Bold', leading=11)
        details_value_style = ParagraphStyle(name='DetailsValueStyle', fontSize=9, fontName='Helvetica', leading=11)
        table_header_style = ParagraphStyle(name='TableHeaderStyle', fontSize=9, fontName='Helvetica-Bold', leading=11, textColor=table_header_text, alignment=1)
        footer_style = ParagraphStyle(name='FooterStyle', fontSize=8, fontName='Helvetica', alignment=1, spaceBefore=12, textColor=colors.HexColor('#666666'))
        
        # Use a consistent style for normal text
        normal_style = ParagraphStyle(name='Normal', fontSize=9, leading=11, fontName='Helvetica')

        # --- Document Layout ---

        # Header: Garage details with a clean, centered look
        elements.append(Paragraph(client_garage.name, header_style))
        elements.append(Paragraph(client_garage.address or 'Kathmandu, Nepal', subheader_style))
        if client_garage.contact:
            elements.append(Paragraph(f"Contact: {client_garage.contact}", subheader_style))
        if client_garage.email:
            elements.append(Paragraph(f"Email: {client_garage.email}", subheader_style))
        elements.append(Spacer(1, 0.2 * inch))

        # Bill and Customer Details (two columns for better organization)
        details_data = [
            [
                Paragraph(f"<b>Bill No:</b> {bill.bill_no}", normal_style), 
                Paragraph(f"<b>Date:</b> {bill.created_at.strftime('%Y-%m-%d')}", normal_style)
            ],
            [
                Paragraph(f"<b>Customer:</b> {bill.customer.name if bill.customer else 'Anonymous'}", normal_style), 
                Paragraph(f"<b>Phone:</b> {bill.customer.phone if bill.customer and bill.customer.phone else ''}", normal_style)
            ],
            [
                Paragraph(f"<b>Vehicle:</b> {bill.vehicle.vehicle_number if bill.vehicle and bill.vehicle.vehicle_number else ''}", normal_style),
                Paragraph(f"<b>Order No:</b> {bill.service_order.order_no if bill.service_order else ''}", normal_style)
            ]
        ]
        
        details_table = Table(details_data, colWidths=[3.25*inch, 3.25*inch])
        details_table.setStyle(TableStyle([
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('BACKGROUND', (0, 0), (-1, -1), header_bg_color),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CCCCCC')),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#CCCCCC'))
        ]))
        elements.append(details_table)
        elements.append(Spacer(1, 0.2 * inch))

        # Items Table (with enhanced styling)
        data = [
            [
                Paragraph("<b>Item Description</b>", table_header_style), 
                Paragraph("<b>Qty</b>", table_header_style), 
                Paragraph("<b>Price</b>", table_header_style), 
                Paragraph("<b>Total</b>", table_header_style)
            ]
        ]
        
        for bi in bill.bill_items.all():
            data.append([
                Paragraph(bi.name, normal_style),
                Paragraph(str(bi.quantity), normal_style),
                Paragraph(f"NPR {bi.price:.2f}", normal_style),
                Paragraph(f"NPR {(bi.price * bi.quantity):.2f}", normal_style)
            ])
            
        items_table = Table(data, colWidths=[3.5*inch, 0.8*inch, 1.2*inch, 1.2*inch])
        items_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), table_header_bg),
            ('TEXTCOLOR', (0, 0), (-1, 0), table_header_text),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CCCCCC')),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#CCCCCC')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ]))
        elements.append(items_table)
        elements.append(Spacer(1, 0.2 * inch))

        # Summary Section (cleaner, two-column layout)
        subtotal = sum(bi.price * bi.quantity for bi in bill.bill_items.all())
        discount_amount = bill.discount_value if bill.discount_type == 'amount' else (subtotal * bill.discount_value / 100)
        
        summary_data = [
            [Paragraph("<b>Subtotal:</b>", details_label_style), Paragraph(f"NPR {subtotal:.2f}", details_value_style)],
            [Paragraph(f"<b>Discount ({'amount' if bill.discount_type == 'amount' else str(bill.discount_value) + '%'}):</b>", details_label_style), Paragraph(f"NPR {discount_amount:.2f}", details_value_style)],
            [Paragraph("<b>VAT (13%):</b>", details_label_style), Paragraph(f"NPR {bill.tax:.2f}", details_value_style)],
            [Paragraph("<b>Credit:</b>", details_label_style), Paragraph(f"NPR {bill.credit_amount:.2f}", details_value_style) if bill.credit_amount > 0 else ''],
            [Paragraph("<b>Total:</b>", ParagraphStyle(name='TotalStyle', fontSize=11, fontName='Helvetica-Bold', leading=14, textColor=colors.HexColor('#000000'))), Paragraph(f"NPR {bill.total:.2f}", ParagraphStyle(name='TotalStyle', fontSize=11, fontName='Helvetica-Bold', leading=14, textColor=colors.HexColor('#000000')))],
            [Paragraph("<b>Payment Mode:</b>", details_label_style), Paragraph(bill.payment_mode.upper(), details_value_style)]
        ]
        
        summary_table = Table(summary_data, colWidths=[3.25*inch, 3.25*inch])
        summary_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('LINEBELOW', (0, -2), (-1, -2), 1, colors.black),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ]))
        elements.append(summary_table)

        # Footer
        elements.append(Spacer(1, 0.5 * inch))
        elements.append(Paragraph("Thank you for your business!", footer_style))
        elements.append(Paragraph("This is a computer-generated invoice and does not require a signature.", footer_style))
        
        doc.build(elements)
        
        pdf = buffer.getvalue()
        buffer.close()
        
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="bill_{bill.bill_no}.pdf"'
        response.write(pdf)
        return response
    
    except ClientGarage.DoesNotExist:
        logger.error(f"No ClientGarage found for user {request.user.username}")
        return JsonResponse({'status': 'error', 'message': 'Client garage not found'}, status=404)
    except Bill.DoesNotExist:
        logger.error(f"Bill {bill_id} not found for user {request.user.username}")
        return JsonResponse({'status': 'error', 'message': 'Bill not found'}, status=404)
    except Exception as e:
        logger.error(f"Error in generate_bill_pdf for user {request.user.username}: {str(e)}")
        return JsonResponse({'status': 'error', 'message': f'Failed to generate PDF: {str(e)}'}, status=500)
    
from django.db.models import Count, Sum
from django.db.models.functions import TruncDate

@login_required
def get_tax_settings(request):
    try:
        client_garage = ClientGarage.objects.get(user=request.user)
        tax_setting = TaxSetting.objects.filter(client_garage=client_garage).first()
        if not tax_setting:
            tax_setting = TaxSetting.objects.create(
                client_garage=client_garage,
                tax_rate=13.00,
                include_in_bill=True
            )
        return JsonResponse({
            'tax_rate': float(tax_setting.tax_rate),
            'include_in_bill': tax_setting.include_in_bill
        })
    except ClientGarage.DoesNotExist:
        logger.error(f"No ClientGarage found for user {request.user.username}")
        return JsonResponse({'status': 'error', 'message': 'Client garage not found'}, status=404)
    except Exception as e:
        logger.error(f"Error getting tax settings for user {request.user.username}: {str(e)}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

from django.db.models import Count, Sum
from django.db.models.functions import TruncDate

@login_required
def get_tax_settings(request):
    try:
        client_garage = ClientGarage.objects.get(user=request.user)
        tax_setting = TaxSetting.objects.filter(client_garage=client_garage).first()
        if not tax_setting:
            tax_setting = TaxSetting.objects.create(
                client_garage=client_garage,
                tax_rate=13.00,
                include_in_bill=True
            )
        return JsonResponse({
            'tax_rate': float(tax_setting.tax_rate),
            'include_in_bill': tax_setting.include_in_bill
        })
    except ClientGarage.DoesNotExist:
        logger.error(f"No ClientGarage found for user {request.user.username}")
        return JsonResponse({'status': 'error', 'message': 'Client garage not found'}, status=404)
    except Exception as e:
        logger.error(f"Error getting tax settings for user {request.user.username}: {str(e)}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from django.http import JsonResponse
import logging

logger = logging.getLogger(__name__)

@login_required
def get_daily_summary(request):
    try:
        client_garage = ClientGarage.objects.get(user=request.user)
        summary = Bill.objects.filter(
            client_garage=client_garage,
            status__in=['Completed', 'Credit']
        ).annotate(
            date=TruncDate('created_at')
        ).values('date').annotate(
            total_bills=Count('id'),
            total_amount=Sum('total')  # ✅ Fixed quote
        ).order_by('-date')[:5]  # Last 5 days

        return JsonResponse({
            'summary': [
                {
                    'date': item['date'].strftime('%Y-%m-%d'),
                    'total_bills': item['total_bills'],
                    'total_amount': float(item['total_amount']) if item['total_amount'] else 0.0
                }
                for item in summary
            ]
        })
    except ClientGarage.DoesNotExist:
        logger.error(f"No ClientGarage found for user {request.user.username}")
        return JsonResponse({'status': 'error', 'message': 'Client garage not found'}, status=404)
    except Exception as e:
        logger.error(f"Error getting daily summary for user {request.user.username}: {str(e)}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
