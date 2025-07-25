from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.db.models import Q
from datetime import datetime, timedelta
from garage.models import (
    ServiceOrderItem, User, ClientGarage, Customer, Vehicle, ServiceOrder, Bill,
    VehicleCompany, VehicleModel, VehicleType, ServiceType
)
from django.db import models
import json
import logging

logger = logging.getLogger(__name__)

@login_required
def add_vehicle(request):
    logger.info(f"User {request.user.username} accessed add_vehicle view")
    if request.user.is_superuser or request.user.role != 'admin':
        logger.info(f"Redirecting user {request.user.username} with role {request.user.role} to {request.user.role}/dashboard/")
        return redirect(f'/{request.user.role}/dashboard/')
    
    try:
        client_garage = ClientGarage.objects.get(user=request.user)
        logger.info(f"Found ClientGarage {client_garage.name} for user {request.user.username}")
        companies = VehicleCompany.objects.filter(client_garage=client_garage)
        vehicle_types = VehicleType.objects.filter(client_garage=client_garage)
        service_types = ServiceType.objects.filter(client_garage=client_garage)
        mechanics = User.objects.filter(client_garage=client_garage)
        
        context = {
            'user': request.user,
            'companies': companies,
            'vehicle_types': vehicle_types,
            'service_types': service_types,
            'mechanics': mechanics,
        }
        logger.debug(f"Rendering add_vehicle.html with context: {context}")
        return render(request, 'admin/add_vehicle.html', context)
    except ClientGarage.DoesNotExist:
        logger.error(f"No ClientGarage found for user {request.user.username}")
        return JsonResponse({'status': 'error', 'message': 'Client garage not found for this user'}, status=404)
    except Exception as e:
        logger.error(f"Error in add_vehicle for user {request.user.username}: {str(e)}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@login_required
def search_customer(request):
    query = request.GET.get('q', '')
    logger.info(f"User {request.user.username} searching customers with query: {query}")
    try:
        client_garage = ClientGarage.objects.get(user=request.user)
        logger.info(f"Found ClientGarage {client_garage.name} for user {request.user.username}")
        customers = Customer.objects.filter(
            client_garage=client_garage
        ).filter(
            Q(name__icontains=query) | Q(phone__icontains=query)
        )[:10]
        
        results = [
            {
                'id': customer.id,
                'name': customer.name,
                'phone': customer.phone or '',
                'visits': [
                    {
                        'orderNo': order.order_no,
                        'date': order.created_date.strftime('%Y-%m-%d'),
                        'service': ', '.join(order.service_type.values_list('name', flat=True))
                    }
                    for order in customer.serviceorder_set.all()[:5]
                ]
            }
            for customer in customers
        ]
        logger.debug(f"Returning {len(results)} customer search results")
        return JsonResponse({'customers': results})
    except ClientGarage.DoesNotExist:
        logger.error(f"No ClientGarage found for user {request.user.username}")
        return JsonResponse({'status': 'error', 'message': 'Client garage not found for this user'}, status=404)
    except Exception as e:
        logger.error(f"Error in search_customer for user {request.user.username}: {str(e)}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@login_required
def search_vehicle(request):
    query = request.GET.get('q', '')
    logger.info(f"User {request.user.username} searching vehicles with query: {query}")
    try:
        client_garage = ClientGarage.objects.get(user=request.user)
        logger.info(f"Found ClientGarage {client_garage.name} for user {request.user.username}")
        vehicles = Vehicle.objects.filter(
            client_garage=client_garage,
            vehicle_number__icontains=query
        )[:10]
        
        results = [
            {
                'id': vehicle.id,
                'vehicleNumber': vehicle.vehicle_number,
                'company': vehicle.company.id if vehicle.company else None,
                'model': vehicle.model.id if vehicle.model else None,
                'type': vehicle.type.id if vehicle.type else None,
                'customerId': vehicle.customer.id if vehicle.customer else None,
                'customerName': vehicle.customer.name if vehicle.customer else 'Anonymous',
                'phone': vehicle.customer.phone if vehicle.customer else ''
            }
            for vehicle in vehicles
        ]
        logger.debug(f"Returning {len(results)} vehicle search results")
        return JsonResponse({'vehicles': results})
    except ClientGarage.DoesNotExist:
        logger.error(f"No ClientGarage found for user {request.user.username}")
        return JsonResponse({'status': 'error', 'message': 'Client garage not found for this user'}, status=404)
    except Exception as e:
        logger.error(f"Error in search_vehicle for user {request.user.username}: {str(e)}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@login_required
def get_vehicle_models(request):
    company_id = request.GET.get('company_id')
    logger.info(f"User {request.user.username} fetching vehicle models for company_id: {company_id}")
    try:
        client_garage = ClientGarage.objects.get(user=request.user)
        logger.info(f"Found ClientGarage {client_garage.name} for user {request.user.username}")
        models = VehicleModel.objects.filter(
            company_id=company_id,
            client_garage=client_garage
        ).values('id', 'name')
        models_list = list(models)
        logger.debug(f"Returning {len(models_list)} vehicle models")
        return JsonResponse({'models': models_list})
    except ClientGarage.DoesNotExist:
        logger.error(f"No ClientGarage found for user {request.user.username}")
        return JsonResponse({'status': 'error', 'message': 'Client garage not found for this user'}, status=404)
    except Exception as e:
        logger.error(f"Error in get_vehicle_models for user {request.user.username}: {str(e)}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@login_required
def add_vehicle_and_order(request):
    if request.method == 'POST':
        logger.info(f"User {request.user.username} submitting add_vehicle_and_order")
        logger.debug(f"Raw request.body: {request.body}")

        try:
            data = json.loads(request.body.decode('utf-8'))
            logger.info(f"Parsed JSON data: {data}")

            required_fields = {
                'vehicleNumber': data.get('vehicleNumber'),
                'company': data.get('company'),
                'vehicleModel': data.get('vehicleModel'),
                'complaint': data.get('complaint')
            }
            for field_name, value in required_fields.items():
                if not value or (isinstance(value, str) and not value.strip()):
                    logger.error(f"Missing or empty required field: {field_name}")
                    return JsonResponse({'status': 'error', 'message': f'Missing or empty required field: {field_name}'}, status=400)

            client_garage = ClientGarage.objects.get(user=request.user)
            logger.info(f"Found ClientGarage {client_garage.name} for user {request.user.username}")

            customer_name = data.get('customerName', 'Anonymous').strip()
            phone = data.get('phone', '') if data.get('phone') is not None else ''
            customer = None
            if customer_name != 'Anonymous' or phone:
                customer, _ = Customer.objects.get_or_create(
                    client_garage=client_garage,
                    phone=phone if phone else None,
                    defaults={'name': customer_name}
                )
                if not _ and (customer.name != customer_name or customer.phone != phone):
                    customer.name = customer_name
                    customer.phone = phone if phone else None
                    customer.save()
                    logger.info(f"Updated customer {customer_name} (ID: {customer.id}) with new details")

            vehicle_number = required_fields['vehicleNumber'].strip().upper()
            company_id = required_fields['company']
            model_id = required_fields['vehicleModel']
            vehicle_type_id = data.get('vehicleType')

            try:
                company = VehicleCompany.objects.get(id=company_id, client_garage=client_garage)
                logger.info(f"Found VehicleCompany {company.name} (ID: {company_id})")
            except VehicleCompany.DoesNotExist:
                logger.error(f"Invalid company ID: {company_id}")
                return JsonResponse({'status': 'error', 'message': 'Invalid vehicle company'}, status=400)

            try:
                model = VehicleModel.objects.get(id=model_id, client_garage=client_garage, company=company)
                logger.info(f"Found VehicleModel {model.name} (ID: {model_id})")
            except VehicleModel.DoesNotExist:
                logger.error(f"Invalid model ID: {model_id}")
                return JsonResponse({'status': 'error', 'message': 'Invalid vehicle model'}, status=400)

            v_type = None
            if vehicle_type_id:
                try:
                    v_type = VehicleType.objects.get(id=vehicle_type_id, client_garage=client_garage)
                    logger.info(f"Found VehicleType (ID: {v_type.id})")
                except VehicleType.DoesNotExist:
                    logger.warning(f"VehicleType {vehicle_type_id} not found, proceeding without type")

            vehicle, created = Vehicle.objects.get_or_create(
                client_garage=client_garage,
                vehicle_number=vehicle_number,
                defaults={
                    'customer': customer,
                    'company': company,
                    'model': model,
                    'type': v_type
                }
            )
            logger.info(f"Vehicle {vehicle_number} (ID: {vehicle.id}) {'created' if created else 'retrieved'}")

            complaint = required_fields['complaint'].strip()
            common_services = data.get('commonService', [])
            mechanic_ids = data.get('mechanic_ids', [])
            estimated_hours = int(data.get('estimatedTime', 1))
            helmet_given = data.get('helmetGiven', False)
            key_given = data.get('keyGiven', False)
            logger.info(f"Creating service order with complaint: {complaint}, services: {common_services}, mechanic_ids: {mechanic_ids}")

            last_order = ServiceOrder.objects.filter(client_garage=client_garage).order_by('-id').first()
            order_no = f"ORD{str(last_order.id + 1 if last_order else 1).zfill(3)}"
            logger.info(f"Generated order number: {order_no}")

            estimated_completion = (datetime.now() + timedelta(hours=estimated_hours)).time()
            service_order = ServiceOrder.objects.create(
                client_garage=client_garage,
                order_no=order_no,
                vehicle=vehicle,
                customer=customer,
                complaint=complaint,
                status='in-progress' if mechanic_ids else 'waiting-assignment',
                priority=data.get('priority', 'normal'),
                entry_time=datetime.now().time(),
                estimated_completion=estimated_completion,
                created_date=datetime.now().date(),
                progress=0,
                total_so_far=0,
                helmet_given=helmet_given,
                key_given=key_given
            )
            logger.info(f"Created ServiceOrder {order_no} (ID: {service_order.id})")

            total = 0
            bill_items = []
            for service_name in common_services:
                try:
                    service_type = ServiceType.objects.get(client_garage=client_garage, name=service_name)
                    ServiceOrderItem.objects.create(
                        service_order=service_order,
                        service_type=service_type,
                        price=service_type.base_price
                    )
                    total += service_type.base_price
                    bill_items.append({'name': service_name, 'price': float(service_type.base_price)})
                    service_order.service_type.add(service_type)
                    logger.info(f"Added ServiceOrderItem and ServiceType {service_name} (ID: {service_type.id}) to order {order_no}")
                except ServiceType.DoesNotExist:
                    logger.warning(f"ServiceType {service_name} not found for client_garage {client_garage.id}")
                    continue

            service_order.total_so_far = total
            service_order.save()

            for mechanic_id in mechanic_ids:
                try:
                    mechanic = User.objects.get(id=mechanic_id, client_garage=client_garage, is_superuser=False)
                    service_order.mechanics.add(mechanic)
                    logger.info(f"Assigned mechanic {mechanic.username} (ID: {mechanic_id}) to order {order_no}")
                except User.DoesNotExist:
                    logger.warning(f"Invalid or unauthorized mechanic ID {mechanic_id} for order {order_no}")

            bill_no = f"B{str(datetime.now().timestamp()).replace('.', '')[-3:]}"
            bill = Bill.objects.create(
                client_garage=client_garage,
                bill_no=bill_no,
                service_order=service_order,
                customer=customer,
                vehicle=vehicle,
                status='Generated (In Progress)' if mechanic_ids else 'Pending',
                items=json.dumps(bill_items),
                total=total
            )
            logger.info(f"Created Bill {bill_no} (ID: {bill.id}) for order {order_no}")

            return JsonResponse({
                'status': 'success',
                'order_no': service_order.order_no,
                'bill_no': bill_no,
                'bill_id': bill.id
            })
        except ClientGarage.DoesNotExist:
            logger.error(f"No ClientGarage found for user {request.user.username}")
            return JsonResponse({'status': 'error', 'message': 'Client garage not found for this user'}, status=404)
        except Exception as e:
            logger.error(f"Error in add_vehicle_and_order for user {request.user.username}: {str(e)}")
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

    logger.warning(f"Invalid request method {request.method} by user {request.user.username}")
    return redirect('add_vehicle')


@login_required
def get_service_orders(request):
    logger.info(f"User {request.user.username} fetching service orders with status: {request.GET.get('status', 'all')}, query: {request.GET.get('q', '')}, page: {request.GET.get('page', 1)}")
    try:
        client_garage = ClientGarage.objects.get(user=request.user)
        logger.info(f"Found ClientGarage {client_garage.name} for user {request.user.username}")
        status_filter = request.GET.get('status', 'all')
        search_query = request.GET.get('q', '')
        page = int(request.GET.get('page', 1))
        items_per_page = 5
        
        orders = ServiceOrder.objects.filter(client_garage=client_garage).order_by('-created_date')
        if status_filter != 'all':
            status_list = status_filter.split(',')
            orders = orders.filter(status__in=status_list)
            logger.debug(f"Applied status filter: {status_list}")
        if search_query:
            orders = orders.filter(
                Q(vehicle__vehicle_number__icontains=search_query) |
                Q(customer__name__icontains=search_query)
            )
            logger.debug(f"Applied search query: {search_query}")
        
        total = orders.count()
        start = (page - 1) * items_per_page
        end = start + items_per_page
        paginated_orders = orders[start:end]
        logger.debug(f"Fetched {total} orders, paginated from {start} to {end}")
        
        results = [
            {
                'id': order.id,
                'orderNo': order.order_no,
                'vehicleNumber': order.vehicle.vehicle_number,
                'customerId': order.customer.id if order.customer else None,
                'customerName': order.customer.name if order.customer else 'Anonymous',
                'phone': order.customer.phone if order.customer else '',
                'company': order.vehicle.company.id if order.vehicle.company else None,
                'companyName': order.vehicle.company.name if order.vehicle.company else '',
                'model': order.vehicle.model.name if order.vehicle.model else '',
                'modelId': order.vehicle.model.id if order.vehicle.model else None,
                'type': order.vehicle.type.name if order.vehicle.type else '',
                'vehicleTypeId': order.vehicle.type.id if order.vehicle.type else None,
                'complaint': order.complaint,
                'serviceType': [
                    {'name': item.service_type.name, 'price': float(item.price)}
                    for item in order.service_items.all()
                ],
                'mechanics': list(order.mechanics.values_list('id', flat=True)),  # Changed to IDs
                'status': order.status,
                'priority': order.priority,
                'entryTime': order.entry_time.strftime('%I:%M %p'),
                'estimatedCompletion': order.estimated_completion.strftime('%I:%M %p'),
                'createdDate': order.created_date.strftime('%Y-%m-%d'),
                'progress': order.progress,
                'totalSoFar': float(order.total_so_far),
                'helmetGiven': order.helmet_given,
                'keyGiven': order.key_given,
                'billId': Bill.objects.filter(service_order=order).first().id if Bill.objects.filter(service_order=order).exists() else None
            }
            for order in paginated_orders
        ]
        logger.info(f"Returning {len(results)} service orders for page {page}")
        return JsonResponse({
            'orders': results,
            'total': total,
            'page': page,
            'itemsPerPage': items_per_page
        })
    except ClientGarage.DoesNotExist:
        logger.error(f"No ClientGarage found for user {request.user.username}")
        return JsonResponse({'status': 'error', 'message': 'Client garage not found for this user'}, status=404)
    except Exception as e:
        logger.error(f"Error in get_service_orders for user {request.user.username}: {str(e)}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@login_required
def assign_mechanic(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body.decode('utf-8'))
            order_id = data.get('order_id')
            mechanic_ids = data.get('mechanic_ids', [])
            logger.info(f"Parsed JSON data: order_id={order_id}, mechanic_ids={mechanic_ids}")

            if not order_id:
                logger.error("No order_id provided in request")
                return JsonResponse({'status': 'error', 'message': 'Order ID is required'}, status=400)

            try:
                order_id = int(order_id)
            except (TypeError, ValueError):
                logger.error(f"Invalid order_id format: {order_id}, type: {type(order_id)}")
                return JsonResponse({'status': 'error', 'message': 'Invalid order ID format'}, status=400)

            try:
                client_garage = ClientGarage.objects.get(user=request.user)
                service_order = ServiceOrder.objects.get(id=order_id, client_garage=client_garage)
                logger.info(f"Found ServiceOrder {service_order.order_no} (ID: {order_id}) for client_garage {client_garage.name}")
                
                if service_order.status == 'completed':
                    logger.warning(f"Attempt to assign mechanics to completed order {service_order.order_no}")
                    return JsonResponse({'status': 'error', 'message': 'Cannot assign mechanics to completed order'}, status=400)

                current_mechanic_ids = set(service_order.mechanics.values_list('id', flat=True))
                new_mechanic_ids = set(int(mid) for mid in mechanic_ids if mid)
                logger.info(f"Current mechanics: {current_mechanic_ids}, New mechanics: {new_mechanic_ids}")

                # Clear existing mechanics
                service_order.mechanics.clear()
                logger.info(f"Cleared existing mechanics for order {service_order.order_no}")

                # Assign new mechanics
                assigned_mechanics = []
                for mechanic_id in new_mechanic_ids:
                    try:
                        mechanic = User.objects.get(id=mechanic_id, client_garage=client_garage, is_superuser=False)
                        service_order.mechanics.add(mechanic)
                        assigned_mechanics.append(mechanic.username)
                        logger.info(f"Assigned mechanic {mechanic.username} (ID: {mechanic_id}) to order {service_order.order_no}")
                    except User.DoesNotExist:
                        logger.warning(f"Invalid or unauthorized mechanic ID {mechanic_id} for order {service_order.order_no}")
                        continue

                # Update order status
                service_order.status = 'in-progress' if new_mechanic_ids else 'waiting-assignment'
                service_order.save()
                logger.info(f"Updated order {service_order.order_no} status to {service_order.status}")

                # Update bill status
                bill = Bill.objects.filter(service_order=service_order).first()
                if bill:
                    bill.status = 'Generated (In Progress)' if new_mechanic_ids else 'Pending'
                    bill.save()
                    logger.info(f"Updated bill {bill.bill_no} status to {bill.status}")

                return JsonResponse({
                    'status': 'success',
                    'message': f"Mechanics assigned to order {service_order.order_no}: {', '.join(assigned_mechanics) if assigned_mechanics else 'None'}"
                })
            except ClientGarage.DoesNotExist:
                logger.error(f"No ClientGarage found for user {request.user.username}")
                return JsonResponse({'status': 'error', 'message': 'Client garage not found for this user'}, status=404)
            except ServiceOrder.DoesNotExist:
                logger.error(f"ServiceOrder {order_id} not found for client_garage")
                return JsonResponse({'status': 'error', 'message': 'Service order not found'}, status=404)
            except Exception as e:
                logger.error(f"Error in assign_mechanic for user {request.user.username}: {str(e)}")
                return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON in assign_mechanic request for user {request.user.username}")
            return JsonResponse({'status': 'error', 'message': 'Invalid JSON data'}, status=400)

    logger.warning(f"Invalid request method {request.method} by user {request.user.username}")
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=405)

@login_required
def get_service_order(request):
    order_id = request.GET.get('order_id')
    logger.info(f"User {request.user.username} fetching service order {order_id}")
    try:
        client_garage = ClientGarage.objects.get(user=request.user)
        logger.info(f"Found ClientGarage {client_garage.name} for user {request.user.username}")
        try:
            order = ServiceOrder.objects.get(id=order_id, client_garage=client_garage)
            logger.info(f"Found ServiceOrder {order.order_no} (ID: {order_id})")
            result = {
                'id': order.id,
                'orderNo': order.order_no,
                'vehicleNumber': order.vehicle.vehicle_number,
                'customerId': order.customer.id if order.customer else None,
                'customerName': order.customer.name if order.customer else 'Anonymous',
                'phone': order.customer.phone if order.customer else '',
                'company': order.vehicle.company.id if order.vehicle.company else None,
                'companyName': order.vehicle.company.name if order.vehicle.company else '',
                'model': order.vehicle.model.name if order.vehicle.model else '',
                'modelId': order.vehicle.model.id if order.vehicle.model else None,
                'type': order.vehicle.type.name if order.vehicle.type else '',
                'vehicleTypeId': order.vehicle.type.id if order.vehicle.type else None,
                'complaint': order.complaint,
                'serviceType': [
                    {'name': item.service_type.name, 'price': float(item.price)}
                    for item in order.service_items.all()
                ],
                'mechanics': list(order.mechanics.values_list('id', flat=True)),  # Changed to IDs
                'status': order.status,
                'priority': order.priority,
                'entryTime': order.entry_time.strftime('%I:%M %p'),
                'estimatedCompletion': order.estimated_completion.strftime('%I:%M %p'),
                'createdDate': order.created_date.strftime('%Y-%m-%d'),
                'progress': order.progress,
                'totalSoFar': float(order.total_so_far),
                'helmetGiven': order.helmet_given,
                'keyGiven': order.key_given,
                'billId': Bill.objects.filter(service_order=order).first().id if Bill.objects.filter(service_order=order).exists() else None
            }
            logger.debug(f"Returning service order details: {result}")
            return JsonResponse({'status': 'success', 'order': result})
        except ServiceOrder.DoesNotExist:
            logger.error(f"ServiceOrder {order_id} not found for client_garage")
            return JsonResponse({'status': 'error', 'message': 'Service order not found'}, status=404)
    except ClientGarage.DoesNotExist:
        logger.error(f"No ClientGarage found for user {request.user.username}")
        return JsonResponse({'status': 'error', 'message': 'Client garage not found for this user'}, status=404)
    except Exception as e:
        logger.error(f"Error in get_service_order for user {request.user.username}: {str(e)}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    
@login_required
def update_service_order(request):
    if request.method == 'POST':
        logger.info(f"User {request.user.username} updating service order")
        logger.debug(f"Raw request.body: {request.body}")

        try:
            data = json.loads(request.body.decode('utf-8'))
            logger.info(f"Parsed JSON data: {data}")

            order_id = data.get('order_id')
            if not order_id:
                logger.error("No order_id provided in request")
                return JsonResponse({'status': 'error', 'message': 'Order ID is required'}, status=400)

            try:
                order_id = int(order_id)
            except (TypeError, ValueError):
                logger.error(f"Invalid order_id format: {order_id}, type: {type(order_id)}")
                return JsonResponse({'status': 'error', 'message': 'Invalid order ID format'}, status=400)

            required_fields = {
                'vehicleNumber': data.get('vehicleNumber'),
                'company': data.get('company'),
                'vehicleModel': data.get('vehicleModel'),
                'complaint': data.get('complaint')
            }
            for field_name, value in required_fields.items():
                if not value or (isinstance(value, str) and not value.strip()):
                    logger.error(f"Missing or empty required field: {field_name}")
                    return JsonResponse({'status': 'error', 'message': f'Missing or empty required field: {field_name}'}, status=400)

            client_garage = ClientGarage.objects.get(user=request.user)
            logger.info(f"Found ClientGarage {client_garage.name} for user {request.user.username}")

            try:
                service_order = ServiceOrder.objects.get(id=order_id, client_garage=client_garage)
                logger.info(f"Found ServiceOrder {service_order.order_no} (ID: {order_id})")
            except ServiceOrder.DoesNotExist:
                logger.error(f"ServiceOrder {order_id} not found for client_garage")
                return JsonResponse({'status': 'error', 'message': 'Service order not found'}, status=404)

            if service_order.status == 'completed':
                logger.warning(f"Attempt to update completed order {service_order.order_no}")
                return JsonResponse({'status': 'error', 'message': 'Cannot update completed order'}, status=400)

            customer_name = data.get('customerName', 'Anonymous').strip()
            phone = data.get('phone', '') if data.get('phone') is not None else ''
            customer = None
            if customer_name != 'Anonymous' or phone:
                customer, _ = Customer.objects.get_or_create(
                    client_garage=client_garage,
                    phone=phone if phone else None,
                    defaults={'name': customer_name}
                )
                if not _ and (customer.name != customer_name or customer.phone != phone):
                    customer.name = customer_name
                    customer.phone = phone if phone else None
                    customer.save()
                    logger.info(f"Updated customer {customer_name} (ID: {customer.id}) with new details")

            vehicle_number = required_fields['vehicleNumber'].strip().upper()
            company_id = required_fields['company']
            model_id = required_fields['vehicleModel']
            vehicle_type_id = data.get('vehicleType')

            try:
                company = VehicleCompany.objects.get(id=company_id, client_garage=client_garage)
                logger.info(f"Found VehicleCompany {company.name} (ID: {company_id})")
            except VehicleCompany.DoesNotExist:
                logger.error(f"Invalid company ID: {company_id}")
                return JsonResponse({'status': 'error', 'message': 'Invalid vehicle company'}, status=400)

            try:
                model = VehicleModel.objects.get(id=model_id, client_garage=client_garage, company=company)
                logger.info(f"Found VehicleModel {model.name} (ID: {model_id})")
            except VehicleModel.DoesNotExist:
                logger.error(f"Invalid model ID: {model_id}")
                return JsonResponse({'status': 'error', 'message': 'Invalid vehicle model'}, status=400)

            v_type = None
            if vehicle_type_id:
                try:
                    v_type = VehicleType.objects.get(id=vehicle_type_id, client_garage=client_garage)
                    logger.info(f"Found VehicleType (ID: {v_type.id})")
                except VehicleType.DoesNotExist:
                    logger.warning(f"VehicleType {vehicle_type_id} not found, proceeding without type")

            vehicle, created = Vehicle.objects.get_or_create(
                client_garage=client_garage,
                vehicle_number=vehicle_number,
                defaults={
                    'customer': customer,
                    'company': company,
                    'model': model,
                    'type': v_type
                }
            )
            if not created and (
                vehicle.customer != customer or
                vehicle.company != company or
                vehicle.model != model or
                vehicle.type != v_type
            ):
                vehicle.customer = customer
                vehicle.company = company
                vehicle.model = model
                vehicle.type = v_type
                vehicle.save()
                logger.info(f"Updated vehicle {vehicle_number} (ID: {vehicle.id}) with new details")

            service_order.vehicle = vehicle
            service_order.customer = customer
            service_order.complaint = required_fields['complaint'].strip()
            service_order.priority = data.get('priority', 'normal')
            service_order.helmet_given = data.get('helmetGiven', False)
            service_order.key_given = data.get('keyGiven', False)
            estimated_hours = int(data.get('estimatedTime', 1))
            service_order.estimated_completion = (datetime.now() + timedelta(hours=estimated_hours)).time()

            # Clear existing service items
            service_order.service_items.all().delete()
            service_order.service_type.clear()
            logger.info(f"Cleared existing service items for order {service_order.order_no}")

            # Add new service items
            total = 0
            bill_items = []
            common_services = data.get('commonService', [])
            for service_name in common_services:
                try:
                    service_type = ServiceType.objects.get(client_garage=client_garage, name=service_name)
                    ServiceOrderItem.objects.create(
                        service_order=service_order,
                        service_type=service_type,
                        price=service_type.base_price
                    )
                    total += service_type.base_price
                    bill_items.append({'name': service_name, 'price': float(service_type.base_price)})
                    service_order.service_type.add(service_type)
                    logger.info(f"Added ServiceOrderItem and ServiceType {service_name} (ID: {service_type.id}) to order {service_order.order_no}")
                except ServiceType.DoesNotExist:
                    logger.warning(f"ServiceType {service_name} not found for client_garage {client_garage.id}")
                    continue

            service_order.total_so_far = total
            # Update status based on mechanics
            mechanic_ids = data.get('mechanic_ids', [])
            service_order.status = 'in-progress' if mechanic_ids else 'waiting-assignment'

            # Clear existing mechanics
            service_order.mechanics.clear()
            logger.info(f"Cleared existing mechanics for order {service_order.order_no}")

            # Assign new mechanics
            for mechanic_id in mechanic_ids:
                try:
                    mechanic = User.objects.get(id=mechanic_id, client_garage=client_garage, is_superuser=False)
                    service_order.mechanics.add(mechanic)
                    logger.info(f"Assigned mechanic {mechanic.username} (ID: {mechanic_id}) to order {service_order.order_no}")
                except User.DoesNotExist:
                    logger.warning(f"Invalid or unauthorized mechanic ID {mechanic_id} for order {service_order.order_no}")
                    continue

            service_order.save()
            logger.info(f"Updated ServiceOrder {service_order.order_no} with new details")

            # Update bill
            bill = Bill.objects.filter(service_order=service_order).first()
            if bill:
                bill.customer = customer
                bill.vehicle = vehicle
                bill.status = 'Generated (In Progress)' if mechanic_ids else 'Pending'
                bill.items = json.dumps(bill_items)
                bill.total = total
                bill.save()
                logger.info(f"Updated bill {bill.bill_no} for order {service_order.order_no}")
            else:
                bill_no = f"B{str(datetime.now().timestamp()).replace('.', '')[-3:]}"
                bill = Bill.objects.create(
                    client_garage=client_garage,
                    bill_no=bill_no,
                    service_order=service_order,
                    customer=customer,
                    vehicle=vehicle,
                    status='Generated (In Progress)' if mechanic_ids else 'Pending',
                    items=json.dumps(bill_items),
                    total=total
                )
                logger.info(f"Created new bill {bill_no} (ID: {bill.id}) for order {service_order.order_no}")

            return JsonResponse({
                'status': 'success',
                'order_no': service_order.order_no,
                'bill_id': bill.id
            })
        except ClientGarage.DoesNotExist:
            logger.error(f"No ClientGarage found for user {request.user.username}")
            return JsonResponse({'status': 'error', 'message': 'Client garage not found for this user'}, status=404)
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON in update_service_order request for user {request.user.username}")
            return JsonResponse({'status': 'error', 'message': 'Invalid JSON data'}, status=400)
        except Exception as e:
            logger.error(f"Error in update_service_order for user {request.user.username}: {str(e)}")
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

    logger.warning(f"Invalid request method {request.method} by user {request.user.username}")
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=405)

@login_required
def staff_list(request):
    logger.info(f"User {request.user.username} fetching staff list")
    try:
        client_garage = ClientGarage.objects.get(user=request.user)
        logger.info(f"Found ClientGarage {client_garage.name} for user {request.user.username}")
        
        mechanics = User.objects.filter(
            client_garage=client_garage,
            is_superuser=False
        ).exclude(
            role='admin'
        ).annotate(
            current_jobs=models.Count('service_orders', filter=Q(service_orders__status__in=['in-progress', 'waiting-assignment']))
        )
        
        results = [
            {
                'id': mechanic.id,
                'username': mechanic.username,
                'status': 'Available' if mechanic.current_jobs < 5 else 'Busy',
                'current_jobs': mechanic.current_jobs
            }
            for mechanic in mechanics
        ]
        logger.debug(f"Returning {len(results)} mechanics")
        return JsonResponse({'mechanics': results})
    
    except ClientGarage.DoesNotExist:
        logger.error(f"No ClientGarage found for user {request.user.username}")
        return JsonResponse({'status': 'error', 'message': 'Client garage not found for this user'}, status=404)
    
    except Exception as e:
        logger.error(f"Error in staff_list for user {request.user.username}: {str(e)}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
