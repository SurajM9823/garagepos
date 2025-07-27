from decimal import Decimal
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.db.models import Sum, Count, Q
from django.core.paginator import Paginator
from garage.models import Supplier, PurchaseOrder, PurchaseOrderItem, SupplierPayment, Part, ClientGarage, ClientFiscalYear, TaxSetting, VehicleCompany, VehicleType, VehicleModel, PartCategory
from django.utils import timezone
from datetime import date, timedelta
import json
import logging
from django.views.decorators.http import require_http_methods

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from garage.models import VehicleType, ClientGarage


# Set up logging
logger = logging.getLogger(__name__)

@login_required
def inventory_management(request):
    if request.user.is_superuser or request.user.role != 'admin':
        return redirect(f'/{request.user.role}/dashboard/')
    return render(request, 'admin/inventory_management.html', {'user': request.user})

@login_required
def get_tax_settings(request):
    if request.user.is_superuser or request.user.role != 'admin':
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    try:
        tax_setting = TaxSetting.objects.filter(client_garage=request.user.client_garage).first()
        if not tax_setting:
            return JsonResponse({'tax_rate': 13.0, 'include_in_bill': True}, status=200)
        return JsonResponse({
            'tax_rate': float(tax_setting.tax_rate),
            'include_in_bill': tax_setting.include_in_bill
        }, status=200)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def create_purchase_order(request):
    if request.user.is_superuser or request.user.role != 'admin':
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            supplier_id = data.get('supplierId')
            payment_mode = data.get('paymentMode')
            items = data.get('items')
            
            if not all([supplier_id, payment_mode, items]):
                return JsonResponse({'error': 'Supplier, payment mode, and items are required'}, status=400)
            
            supplier = Supplier.objects.get(pk=supplier_id, client_garage=request.user.client_garage)
            tax_setting = TaxSetting.objects.filter(client_garage=request.user.client_garage).first()
            tax_rate = tax_setting.tax_rate / 100 if tax_setting and tax_setting.include_in_bill else 0
            subtotal = sum(item['quantity'] * item['rate'] for item in items)
            tax = subtotal * tax_rate
            total = subtotal + tax
            
            if payment_mode == 'credit' and (supplier.current_credit + total) > supplier.credit_limit:
                return JsonResponse({'error': 'Credit limit exceeded'}, status=400)
            
            purchase_no = f"PO{timezone.now().strftime('%Y%m%d%H%M%S')}"
            due_date = None
            if payment_mode == 'credit':
                days = int(supplier.payment_terms.split('-')[0]) if supplier.payment_terms != 'immediate' else 0
                due_date = date.today() + timedelta(days=days)
            
            purchase_order = PurchaseOrder.objects.create(
                client_garage=request.user.client_garage,
                client_fiscal_year=request.user.client_fiscal_year,
                supplier=supplier,
                purchase_no=purchase_no,
                date=date.today(),
                subtotal=subtotal,
                tax=tax,
                total=total,
                payment_mode=payment_mode,
                status='pending' if payment_mode == 'credit' else 'paid',
                due_date=due_date
            )
            
            for item in items:
                part = Part.objects.filter(client_garage=request.user.client_garage, code=item['code']).first()
                vehicle_company = VehicleCompany.objects.filter(client_garage=request.user.client_garage, name=item['vehicle_company']).first() if item.get('vehicle_company') else None
                vehicle_type = VehicleType.objects.filter(client_garage=request.user.client_garage, name=item['vehicle_type']).first() if item.get('vehicle_type') else None
                vehicle_model = VehicleModel.objects.filter(client_garage=request.user.client_garage, name=item['vehicle_model']).first() if item.get('vehicle_model') else None
                if not part:
                    part = Part.objects.create(
                        client_garage=request.user.client_garage,
                        client_fiscal_year=request.user.client_fiscal_year,
                        code=item['code'] or f"PART{timezone.now().strftime('%Y%m%d%H%M%S')}",
                        name=item['name'],
                        category=PartCategory.objects.filter(client_garage=request.user.client_garage, name=supplier.category).first() or PartCategory.objects.filter(client_garage=request.user.client_garage).first(),
                        supplier=supplier,
                        purchase_price=item['rate'],
                        selling_price=item['sellingPrice'],
                        vehicle_company=vehicle_company,
                        vehicle_type=vehicle_type,
                        vehicle_model=vehicle_model,
                        in_stock=item['quantity'],
                        min_stock=5,
                        status='in-stock' if item['quantity'] > 5 else 'low-stock'
                    )
                else:
                    part.in_stock += item['quantity']
                    part.vehicle_company = vehicle_company
                    part.vehicle_type = vehicle_type
                    part.vehicle_model = vehicle_model
                    part.purchase_price = item['rate']
                    part.selling_price = item['sellingPrice']
                    part.last_movement = date.today()
                    part.movement_type = 'added'
                    part.status = 'out-of-stock' if part.in_stock == 0 else 'low-stock' if part.in_stock <= part.min_stock else 'in-stock'
                    part.save()
                
                PurchaseOrderItem.objects.create(
                    purchase_order=purchase_order,
                    part=part,
                    quantity=item['quantity'],
                    rate=item['rate'],
                    amount=item['quantity'] * item['rate']
                )
            
            if payment_mode == 'credit':
                supplier.current_credit += total
                supplier.save()
            
            return JsonResponse({'message': 'Purchase order created successfully'}, status=200)
        except Supplier.DoesNotExist:
            return JsonResponse({'error': 'Supplier not found'}, status=404)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid request method'}, status=400)

# Other views (unchanged)
@login_required
def get_suppliers(request):
    if request.user.is_superuser or request.user.role != 'admin':
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    search_term = request.GET.get('search', '')
    page = int(request.GET.get('page', 1))
    per_page = 9  # 3x3 grid for suppliers
    
    suppliers = Supplier.objects.filter(
        client_garage=request.user.client_garage,
        client_fiscal_year=request.user.client_fiscal_year
    ).filter(
        Q(name__icontains=search_term) | Q(category__icontains=search_term) | Q(phone__icontains=search_term)
    ).order_by('name')
    
    paginator = Paginator(suppliers, per_page)
    page_obj = paginator.get_page(page)
    
    return JsonResponse({
        'suppliers': [{
            'id': s.id,
            'name': s.name,
            'contactPerson': s.contact_person,
            'phone': s.phone,
            'email': s.email,
            'address': s.address,
            'vat': s.vat_number,
            'creditLimit': float(s.credit_limit),
            'currentCredit': float(s.current_credit),
            'paymentTerms': s.payment_terms,
            'category': s.category,
            'status': s.status,
            'lastPurchase': s.purchase_orders.order_by('-date').first().date.strftime('%Y-%m-%d') if s.purchase_orders.exists() else ''
        } for s in page_obj],
        'total_pages': paginator.num_pages,
        'current_page': page
    }, status=200)

@login_required
def save_supplier(request):
    if request.user.is_superuser or request.user.role != 'admin':
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            supplier_id = data.get('id')
            client_garage = request.user.client_garage
            client_fiscal_year = request.user.client_fiscal_year
            
            if not all([data.get('name'), data.get('phone')]):
                return JsonResponse({'error': 'Supplier name and phone are required'}, status=400)
            
            if supplier_id:
                supplier = Supplier.objects.get(pk=supplier_id, client_garage=client_garage)
                if Supplier.objects.filter(client_garage=client_garage, name=data['name']).exclude(pk=supplier_id).exists():
                    return JsonResponse({'error': 'Supplier name already exists'}, status=400)
            else:
                if Supplier.objects.filter(client_garage=client_garage, name=data['name']).exists():
                    return JsonResponse({'error': 'Supplier name already exists'}, status=400)
                supplier = Supplier(client_garage=client_garage, client_fiscal_year=client_fiscal_year)
            
            supplier.name = data['name']
            supplier.contact_person = data.get('contactPerson')
            supplier.phone = data['phone']
            supplier.email = data.get('email')
            supplier.address = data.get('address')
            supplier.vat_number = data.get('vat')
            supplier.category = data.get('category', 'spare-parts')
            supplier.credit_limit = float(data.get('creditLimit', 0))
            supplier.payment_terms = data.get('paymentTerms', '30-days')
            supplier.status = data.get('status', 'active')
            supplier.save()
            
            return JsonResponse({'message': 'Supplier saved successfully'}, status=200)
        except Supplier.DoesNotExist:
            return JsonResponse({'error': 'Supplier not found'}, status=404)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid request method'}, status=400)

@login_required
def get_purchase_orders(request):
    if request.user.is_superuser or request.user.role != 'admin':
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    page = int(request.GET.get('page', 1))
    per_page = 10
    
    purchase_orders = PurchaseOrder.objects.filter(
        client_garage=request.user.client_garage,
        client_fiscal_year=request.user.client_fiscal_year
    ).order_by('-date')
    
    paginator = Paginator(purchase_orders, per_page)
    page_obj = paginator.get_page(page)
    
    return JsonResponse({
        'purchase_orders': [{
            'id': po.id,
            'purchaseNo': po.purchase_no,
            'supplier': po.supplier.name,
            'supplierId': str(po.supplier.id), 
            'date': po.date.strftime('%Y-%m-%d'),
            'amount': float(po.total),
            'paymentMode': po.payment_mode,
            'status': po.status,
            'dueDate': po.due_date.strftime('%Y-%m-%d') if po.due_date else '',
            'items': [{
                'name': item.part.name,
                'quantity': item.quantity,
                'rate': float(item.rate),
                'amount': float(item.amount),
                'code': item.part.code
            } for item in po.items.all()]
        } for po in page_obj],
        'total_pages': paginator.num_pages,
        'current_page': page
    }, status=200)

@login_required
def make_supplier_payment(request):
    if request.user.is_superuser or request.user.role != 'admin':
        logger.warning(f"Unauthorized access attempt by user {request.user.username}")
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            supplier_id = data.get('supplierId')
            amount = Decimal(str(data.get('amount')))  # Convert to Decimal
            purchase_order_id = data.get('purchaseOrderId')

            if not supplier_id:
                logger.warning("Supplier ID is missing in payment request")
                return JsonResponse({'error': 'Supplier ID is required'}, status=400)
            if amount <= 0:
                logger.warning(f"Invalid payment amount: {amount}")
                return JsonResponse({'error': 'Payment amount must be positive'}, status=400)

            supplier = Supplier.objects.get(pk=supplier_id, client_garage=request.user.client_garage)
            if amount > supplier.current_credit:
                logger.warning(f"Payment amount {amount} exceeds current credit {supplier.current_credit}")
                return JsonResponse({'error': 'Payment amount cannot exceed current credit'}, status=400)

            # Create payment record
            payment = SupplierPayment.objects.create(
                client_garage=request.user.client_garage,
                supplier=supplier,
                purchase_order=PurchaseOrder.objects.get(pk=purchase_order_id) if purchase_order_id else None,
                amount=amount,
                payment_date=timezone.now().date()
            )

            # Update supplier's current credit
            supplier.current_credit -= amount
            supplier.save()

            # Update purchase order status if linked
            if purchase_order_id:
                po = PurchaseOrder.objects.get(pk=purchase_order_id, client_garage=request.user.client_garage)
                total_paid = SupplierPayment.objects.filter(purchase_order=po).aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
                po.status = 'paid' if total_paid >= po.total else 'partially_paid'
                po.save()
                logger.info(f"Updated purchase order {po.purchase_no}: status={po.status}, total_paid={total_paid}")

            logger.info(f"Payment of {amount} recorded for supplier {supplier.name} (ID: {supplier.id}) by user {request.user.username}")
            return JsonResponse({'message': 'Payment recorded successfully'}, status=200)

        except Supplier.DoesNotExist:
            logger.warning(f"Supplier ID {supplier_id} not found for client_garage {request.user.client_garage.id}")
            return JsonResponse({'error': 'Supplier not found'}, status=404)
        except PurchaseOrder.DoesNotExist:
            logger.warning(f"Purchase order ID {purchase_order_id} not found for client_garage {request.user.client_garage.id}")
            return JsonResponse({'error': 'Purchase order not found'}, status=404)
        except Exception as e:
            logger.error(f"Error processing payment: {str(e)}")
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid request method'}, status=400)

@login_required
def get_inventory(request):
    if request.user.is_superuser or request.user.role != 'admin':
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    search_term = request.GET.get('search', '')
    category = request.GET.get('category', 'all')
    page = int(request.GET.get('page', 1))
    per_page = 10
    
    parts = Part.objects.filter(
        client_garage=request.user.client_garage,
        client_fiscal_year=request.user.client_fiscal_year
    )
    
    if category != 'all':
        parts = parts.filter(category__name=category)
    if search_term:
        parts = parts.filter(Q(name__icontains=search_term) | Q(code__icontains=search_term))
    
    paginator = Paginator(parts.order_by('name'), per_page)
    page_obj = paginator.get_page(page)
    
    return JsonResponse({
        'parts': [{
            'id': p.id,
            'code': p.code,
            'name': p.name,
            'category': p.category.name,
            'vehicle_company': p.vehicle_company.name if p.vehicle_company else '',
            'vehicle_type': p.vehicle_type.name if p.vehicle_type  else '',
            'vehicle_model': p.vehicle_model.name if p.vehicle_model else '',
            'quantity': p.in_stock,
            'minStock': p.min_stock,
            'purchasePrice': float(p.purchase_price),
            'sellingPrice': float(p.selling_price),
            'supplier': p.supplier.name if p.supplier else '',
            'lastUpdated': p.last_movement.strftime('%Y-%m-%d'),
            'movement': p.movement_type,
            'status': p.status,
            'image': p.image.url if p.image else ''
        } for p in page_obj],
        'total_pages': paginator.num_pages,
        'current_page': page
    }, status=200)

@login_required
def save_inventory(request):
    if request.user.is_superuser or request.user.role != 'admin':
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    if request.method == 'POST':
        try:
            # Support both JSON and multipart/form-data
            if request.content_type.startswith('multipart'):
                data = request.POST
                files = request.FILES
            else:
                data = json.loads(request.body)
                files = None
            part_id = data.get('id')
            client_garage = request.user.client_garage
            client_fiscal_year = request.user.client_fiscal_year
            
            if not data.get('name') or int(data.get('quantity', 0)) < 0:
                return JsonResponse({'error': 'Part name and valid quantity are required'}, status=400)
            
            # Assign default category (first available for the client garage)
            category = PartCategory.objects.filter(client_garage=client_garage).first()
            if not category:
                return JsonResponse({'error': 'No part category exists. Please create a category first.'}, status=400)
            
            vehicle_company = VehicleCompany.objects.filter(client_garage=client_garage, name=data.get('vehicleCompany')).first() if data.get('vehicleCompany') else None
            vehicle_type = VehicleType.objects.filter(client_garage=client_garage, name=data.get('vehicleType')).first() if data.get('vehicleType') else None
            vehicle_model = VehicleModel.objects.filter(client_garage=client_garage, name=data.get('vehicleModel')).first() if data.get('vehicleModel') else None
            
            if part_id:
                part = Part.objects.get(pk=part_id, client_garage=client_garage)
            else:
                part = Part(client_garage=client_garage, client_fiscal_year=client_fiscal_year)
            
            part.name = data['name']
            part.category = category
            part.vehicle_company = vehicle_company
            part.vehicle_type = vehicle_type
            part.vehicle_model = vehicle_model
            part.supplier = None  # Set supplier to None as per requirement
            part.purchase_price = float(data.get('purchasePrice', 0))
            part.selling_price = float(data.get('sellingPrice', 0))
            part.in_stock = int(data.get('quantity', 0))
            part.status = 'out-of-stock' if part.in_stock == 0 else 'in-stock'  # Simplified status without min_stock
            part.last_movement = date.today()
            part.movement_type = 'updated' if part_id else 'added'

            # Handle image upload
            if files and 'image' in files:
                new_image = files['image']
                # Delete old image if exists
                if part.image and part.image.name and part.image.storage.exists(part.image.name):
                    part.image.delete(save=False)
                part.image = new_image
                logger.info(f"User {request.user.username} uploaded image for Part {part.id} ({part.name})")
            part.save()
            
            return JsonResponse({
                'message': 'Inventory item saved successfully',
                'image': part.image.url if part.image else ''
            }, status=200)
        except PartCategory.DoesNotExist:
            return JsonResponse({'error': 'No part category exists. Please create a category first.'}, status=404)
        except Part.DoesNotExist:
            return JsonResponse({'error': 'Part not found'}, status=404)
        except Exception as e:
            logger.error(f"Error saving inventory: {str(e)}")
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid request method'}, status=400)

@login_required
def search_items(request):
    if request.user.is_superuser or request.user.role != 'admin':
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    search_term = request.GET.get('term', '')
    parts = Part.objects.filter(
        client_garage=request.user.client_garage,
        name__istartswith=search_term
    )[:10]
    
    return JsonResponse([{
        'id': p.id,
        'label': p.name,
        'value': p.name,
        'code': p.code,
        'category': p.category.name,
        'purchasePrice': float(p.purchase_price),
        'sellingPrice': float(p.selling_price),
        'vehicle_company': p.vehicle_company.name if p.vehicle_company else '',
        'vehicle_type': p.vehicle_type.name if p.vehicle_type else '',
        'vehicle_model': p.vehicle_model.name if p.vehicle_model else ''
    } for p in parts], safe=False, status=200)

@login_required
def get_vehicle_companies(request):
    if request.user.is_superuser or request.user.role != 'admin':
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    companies = VehicleCompany.objects.filter(client_garage=request.user.client_garage)
    return JsonResponse([{'id': c.id, 'name': c.name} for c in companies], safe=False, status=200)


@login_required
def get_vehicle_types_a(request):
    if request.user.is_superuser or request.user.role != 'admin':
        logger.warning(f"Unauthorized access attempt by user {request.user.username}")
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    try:
        # Use request.user.client_garage directly for simplicity
        client_garage = request.user.client_garage
        if not client_garage:
            logger.error(f"No client_garage assigned to user {request.user.username}")
            return JsonResponse({'error': 'No client garage assigned'}, status=404)
        
        logger.debug(f"User: {request.user.username}, client_garage_id: {client_garage.id}")
        types = VehicleType.objects.filter(client_garage=client_garage).order_by('name')
        logger.debug(f"VehicleType query: {types.query}, count: {types.count()}")
        types_list = [{'id': t.id, 'name': t.name} for t in types]
        logger.debug(f"Returning vehicle types: {types_list}")
        return JsonResponse(types_list, safe=False, status=200)
    except Exception as e:
        logger.error(f"Error in get_vehicle_types for user {request.user.username}: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)
    

@login_required
def get_vehicle_models_a(request):
    if request.user.is_superuser or request.user.role != 'admin':
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    try:
        client_garage = ClientGarage.objects.get(user=request.user)
        company_id = request.GET.get('company_id')
        type_id = request.GET.get('type_id')
        
        models = VehicleModel.objects.filter(client_garage=client_garage).order_by('name')
        if company_id:
            models = models.filter(company_id=company_id)
        if type_id:
            models = models.filter(vehicle_type_id=type_id)
        
        models_list = [{'id': m.id, 'name': m.name} for m in models]
        logger.debug(f"Returning {len(models_list)} vehicle models for company_id: {company_id}, type_id: {type_id}")
        return JsonResponse({'models': models_list}, safe=False, status=200)
    except ClientGarage.DoesNotExist:
        logger.error(f"No ClientGarage found for user {request.user.username}")
        return JsonResponse({'error': 'Client garage not found'}, status=404)
    except Exception as e:
        logger.error(f"Error in get_vehicle_models for user {request.user.username}: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)
    if request.user.is_superuser or request.user.role != 'admin':
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    try:
        client_garage = ClientGarage.objects.get(user=request.user)
        company_id = request.GET.get('company_id')
        type_id = request.GET.get('type_id')
        
        models = VehicleModel.objects.filter(client_garage=client_garage)
        if company_id:
            models = models.filter(company_id=company_id)
        if type_id:
            models = models.filter(vehicle_type_id=type_id)
        
        models_list = [{'id': m.id, 'name': m.name} for m in models]
        logger.debug(f"Returning {len(models_list)} vehicle models for company_id: {company_id}, type_id: {type_id}")
        return JsonResponse({'models': models_list}, safe=False, status=200)
    except ClientGarage.DoesNotExist:
        logger.error(f"No ClientGarage found for user {request.user.username}")
        return JsonResponse({'error': 'Client garage not found'}, status=404)
    except Exception as e:
        logger.error(f"Error in get_vehicle_models for user {request.user.username}: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def upload_part_image(request):
    logger.info(f"Received upload request. POST: {dict(request.POST)}, FILES: {dict(request.FILES)}, GET: {dict(request.GET)}")
    try:
        part_id = request.POST.get('id') or request.GET.get('id')
        logger.info(f"Extracted Part ID: {part_id}")
        if not part_id:
            logger.error("Part ID is missing")
            return JsonResponse({'error': 'Part ID is required'}, status=400)
        part = Part.objects.get(pk=part_id, client_garage=request.user.client_garage)
        logger.info(f"Part found: {part.id} - {part.name}")
        if 'image' not in request.FILES:
            logger.error("No image file provided in request.FILES")
            return JsonResponse({'error': 'No image file provided'}, status=400)
        new_image = request.FILES['image']
        logger.info(f"Image received: {new_image.name}, size: {new_image.size}")
        if part.image and part.image.name and part.image.storage.exists(part.image.name):
            logger.info(f"Deleting old image: {part.image.name}")
            part.image.delete(save=False)
        part.image = new_image
        part.save()
        logger.info(f"User {request.user.username} uploaded image for Part {part.id} ({part.name})")
        return JsonResponse({
            'message': 'Image uploaded successfully',
            'image': part.image.url if part.image else ''
        }, status=200)
    except Part.DoesNotExist:
        logger.error(f"Part with ID {part_id} not found or does not belong to client_garage {request.user.client_garage.id}")
        return JsonResponse({'error': 'Part not found'}, status=404)
    except Exception as e:
        logger.error(f"Error uploading image: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def get_supplier_details(request, supplier_id):
    if request.user.is_superuser or request.user.role != 'admin':
        logger.warning(f"Unauthorized access attempt by user {request.user.username}")
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    try:
        supplier = Supplier.objects.get(pk=supplier_id, client_garage=request.user.client_garage)
        purchase_orders = PurchaseOrder.objects.filter(
            supplier=supplier,
            client_garage=request.user.client_garage
        ).order_by('-date')
        
        total_purchases = purchase_orders.aggregate(total=Sum('total'))['total'] or Decimal('0.00')
        total_paid = SupplierPayment.objects.filter(
            supplier=supplier,
            client_garage=request.user.client_garage
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        
        response_data = {
            'supplier': {
                'id': supplier.id,
                'name': supplier.name,
                'contact_person': supplier.contact_person or '',
                'phone': supplier.phone,
                'email': supplier.email or '',
                'address': supplier.address or '',
                'vat_number': supplier.vat_number or '',
                'category': supplier.category,
                'credit_limit': float(supplier.credit_limit),
                'current_credit': float(supplier.current_credit),
                'payment_terms': supplier.payment_terms,
                'status': supplier.status,
                'last_purchase': supplier.purchase_orders.order_by('-date').first().date.strftime('%Y-%m-%d') if supplier.purchase_orders.exists() else ''
            },
            'purchase_orders': [{
                'id': po.id,
                'purchase_no': po.purchase_no,
                'date': po.date.strftime('%Y-%m-%d'),
                'subtotal': float(po.subtotal),
                'tax': float(po.tax),
                'total': float(po.total),
                'payment_mode': po.payment_mode,
                'status': po.status,
                'due_date': po.due_date.strftime('%Y-%m-%d') if po.due_date else '',
                'items': [{
                    'name': item.part.name,
                    'code': item.part.code,
                    'quantity': item.quantity,
                    'rate': float(item.rate),
                    'amount': float(item.amount),
                    'vehicle_company': item.part.vehicle_company.name if item.part.vehicle_company else '',
                    'vehicle_type': item.part.vehicle_type.name if item.part.vehicle_type else '',
                    'vehicle_model': item.part.vehicle_model.name if item.part.vehicle_model else ''
                } for item in po.items.all()]
            } for po in purchase_orders],
            'summary': {
                'total_purchases': float(total_purchases),
                'total_paid': float(total_paid),
                'outstanding_balance': float(total_purchases - total_paid),
                'total_orders': purchase_orders.count()
            }
        }
        return JsonResponse(response_data, status=200)
    except Supplier.DoesNotExist:
        logger.warning(f"Supplier ID {supplier_id} not found for client_garage {request.user.client_garage.id}")
        return JsonResponse({'error': 'Supplier not found'}, status=404)
    except Exception as e:
        logger.error(f"Error fetching supplier details: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)