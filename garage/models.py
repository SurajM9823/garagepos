from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from datetime import date

from django.forms import ValidationError

class UserManager(BaseUserManager):
    def create_user(self, username, email, password=None, role='staff', client_garage=None, financial_year=None, client_fiscal_year=None, **extra_fields):
        if not username:
            raise ValueError('The Username field must be set')
        if not email:
            raise ValueError('The Email field must be set')
        email = self.normalize_email(email)

        # Allow 'superuser' only if is_superuser is True
        is_superuser = extra_fields.get('is_superuser', False)
        if not is_superuser and role not in ['staff', 'manager', 'cashier', 'mechanic', 'admin']:
            raise ValueError('Role must be staff, manager, cashier, or mechanic for non-superuser accounts')

        user = self.model(
            username=username,
            email=email,
            role=role,
            client_garage=client_garage,
            financial_year=financial_year,
            client_fiscal_year=client_fiscal_year,
            **extra_fields
        )
        user.set_password(password)
        user.plaintext_password = password
        user.save(using=self._db)
        return user

    def create_superuser(self, username, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', 'superuser')
        return self.create_user(username, email, password, **extra_fields)
    
      
class User(AbstractBaseUser, PermissionsMixin):
    ROLES = (
        ('superuser', 'Superuser'),
        ('admin', 'Admin'),
        ('staff', 'Staff'),
        ('manager', 'Manager'),
        ('cashier', 'Cashier'),
        ('mechanic', 'Mechanic'),
    )
    EXPERIENCE_LEVELS = (
        ('less_than_1', 'Less than 1 year'),
        ('1_to_2', '1-2 years'),
        ('3_to_5', '3-5 years'),
        ('5_plus', '5+ years'),
    )
    STATUS_CHOICES = (
        ('active', 'Active'),
        ('break', 'On Break'),
        ('off', 'Off Duty'),
        ('terminated', 'Terminated'),
    )

    username = models.CharField(max_length=150, unique=True)
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=ROLES, default='staff')
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    plaintext_password = models.CharField(max_length=128, blank=True, null=True)
    date_joined = models.DateTimeField(auto_now_add=True)
    client_garage = models.ForeignKey('ClientGarage', on_delete=models.CASCADE, null=True, blank=True)
    financial_year = models.ForeignKey('FinancialYear', on_delete=models.SET_NULL, null=True, blank=True)
    client_fiscal_year = models.ForeignKey('ClientFiscalYear', on_delete=models.SET_NULL, null=True, blank=True)
    
    # New staff-related fields
    phone = models.CharField(max_length=20, blank=True, null=True)
    experience_level = models.CharField(max_length=20, choices=EXPERIENCE_LEVELS, blank=True, null=True)
    specialization = models.CharField(max_length=100, blank=True, null=True)
    base_salary = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, blank=True, null=True)
    previous_dues = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, blank=True, null=True)
    current_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active', blank=True, null=True)
    average_rating = models.DecimalField(max_digits=3, decimal_places=1, default=0.0, blank=True, null=True)
    profile_image = models.ImageField(upload_to='staff_profiles/', blank=True, null=True)

    objects = UserManager()

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['email']

    def __str__(self):
        return self.username


    
class ClientGarage(models.Model):
    name = models.CharField(max_length=100)
    logo = models.ImageField(upload_to='client_logos/', blank=True, null=True)
    address = models.CharField(max_length=255, blank=True, null=True)
    contact = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    currency = models.CharField(max_length=10, default='NPR', blank=True, null=True)
    low_stock_threshold = models.PositiveIntegerField(default=5, blank=True, null=True)
    notifications_enabled = models.BooleanField(default=True, blank=True, null=True)
    whatsapp_enabled = models.BooleanField(default=False, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

class ClientFiscalYear(models.Model):
    STATUS_CHOICES = (
        ('active', 'Active'),
        ('inactive', 'Inactive'),
    )
    client_garage = models.ForeignKey('ClientGarage', on_delete=models.CASCADE, related_name='fiscal_years')
    name = models.CharField(max_length=50)
    type = models.CharField(max_length=20, choices=(('fiscal', 'Fiscal'), ('calendar', 'Calendar')), default='fiscal')
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.client_garage.name} - {self.name}"

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)  # Save first to ensure PK is assigned

        if self.status == 'active':
            # Now safe to use self in queries
            ClientFiscalYear.objects.filter(client_garage=self.client_garage).exclude(pk=self.pk).update(status='inactive')
            User.objects.filter(client_garage=self.client_garage).update(client_fiscal_year=self)



from django.db import models, IntegrityError
import logging

logger = logging.getLogger(__name__)

from django.db import models, IntegrityError
import logging

logger = logging.getLogger(__name__)

from django.db import models, IntegrityError
import logging

logger = logging.getLogger(__name__)

class FinancialYear(models.Model):
    STATUS_CHOICES = (
        ('active', 'Active'),
        ('inactive', 'Inactive'),
    )
    name = models.CharField(max_length=50, unique=True)
    type = models.CharField(max_length=20, choices=(('fiscal', 'Fiscal'), ('calendar', 'Calendar')), default='fiscal')
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Save the instance first to assign a primary key
        super().save(*args, **kwargs)
        
        if self.status == 'active':
            try:
                # Deactivate other FinancialYear instances
                FinancialYear.objects.exclude(pk=self.pk).update(status='inactive')
                logger.info(f"Set all other FinancialYear instances to inactive for {self.name}")
            except Exception as e:
                logger.error(f"Error updating other FinancialYear statuses: {str(e)}")
                raise

            try:
                # Update users with a valid client_garage
                User.objects.filter(client_garage__isnull=False).update(financial_year=self)
                logger.info(f"Updated relevant User objects to reference FinancialYear {self.name}")
            except IntegrityError as e:
                logger.error(f"IntegrityError updating User financial_year: {str(e)}")
                raise ValueError(f"Cannot update User financial_year: {str(e)}")
            except Exception as e:
                logger.error(f"Unexpected error updating User financial_year: {str(e)}")
                raise
                    

class SoftwareInfo(models.Model):
    name = models.CharField(max_length=100)
    logo = models.ImageField(upload_to='software_logos/', blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    invoice_prefix = models.CharField(max_length=10, default='INV-', blank=True, null=True)
    language = models.CharField(max_length=10, default='en', blank=True, null=True)
    backup_frequency = models.CharField(max_length=20, choices=(('Daily', 'Daily'), ('Weekly', 'Weekly'), ('Monthly', 'Monthly')), default='Weekly', blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

# Add these new models at the end of the file
class TaxSetting(models.Model):
    client_garage = models.ForeignKey('ClientGarage', on_delete=models.CASCADE, related_name='tax_settings')
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=13.00)
    include_in_bill = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Tax for {self.client_garage.name} - {self.tax_rate}%"

class ServiceType(models.Model):
    client_garage = models.ForeignKey('ClientGarage', on_delete=models.CASCADE, related_name='service_types')
    name = models.CharField(max_length=100)
    category = models.CharField(max_length=100)
    base_price = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} - {self.client_garage.name}"

class PartCategory(models.Model):
    client_garage = models.ForeignKey('ClientGarage', on_delete=models.CASCADE, related_name='part_categories')
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} - {self.client_garage.name}"

class Role(models.Model):
    client_garage = models.ForeignKey('ClientGarage', on_delete=models.CASCADE, related_name='roles')
    name = models.CharField(max_length=50)
    description = models.TextField(blank=True, null=True)
    permissions = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} - {self.client_garage.name}"

class VehicleCompany(models.Model):
    client_garage = models.ForeignKey('ClientGarage', on_delete=models.CASCADE, related_name='vehicle_companies')
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} - {self.client_garage.name}"

class VehicleType(models.Model):
    client_garage = models.ForeignKey('ClientGarage', on_delete=models.CASCADE, related_name='vehicle_types')
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} - {self.client_garage.name}"

class VehicleModel(models.Model):
    client_garage = models.ForeignKey('ClientGarage', on_delete=models.CASCADE, related_name='vehicle_models')
    name = models.CharField(max_length=100)
    company = models.ForeignKey('VehicleCompany', on_delete=models.CASCADE, related_name='models')
    vehicle_type = models.ForeignKey('VehicleType', on_delete=models.CASCADE, related_name='models')
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} - {self.client_garage.name}"

class Customer(models.Model):
    client_garage = models.ForeignKey('ClientGarage', on_delete=models.CASCADE, related_name='customers')
    name = models.CharField(max_length=100, default='Anonymous')
    phone = models.CharField(max_length=20, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} - {self.client_garage.name}"

class Vehicle(models.Model):
    client_garage = models.ForeignKey('ClientGarage', on_delete=models.CASCADE, related_name='vehicles')
    vehicle_number = models.CharField(max_length=20, unique=True)
    customer = models.ForeignKey('Customer', on_delete=models.SET_NULL, null=True, blank=True)
    company = models.ForeignKey('VehicleCompany', on_delete=models.CASCADE)
    model = models.ForeignKey('VehicleModel', on_delete=models.CASCADE)
    type = models.ForeignKey('VehicleType', on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.vehicle_number} - {self.client_garage.name}"

class ServiceOrder(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('in-progress', 'In Progress'),
        ('waiting-assignment', 'Waiting Assignment'),
        ('completed', 'Completed'),
    )
    PRIORITY_CHOICES = (
        ('urgent', 'Urgent'),
        ('normal', 'Normal'),
    )
    client_garage = models.ForeignKey('ClientGarage', on_delete=models.CASCADE, related_name='service_orders')
    order_no = models.CharField(max_length=10, unique=True)
    vehicle = models.ForeignKey('Vehicle', on_delete=models.CASCADE)
    customer = models.ForeignKey('Customer', on_delete=models.SET_NULL, null=True, blank=True)
    complaint = models.TextField()
    service_type = models.ManyToManyField('ServiceType')
    mechanics = models.ManyToManyField('User', related_name='service_orders')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='waiting-assignment')
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='normal')
    entry_time = models.TimeField()
    estimated_completion = models.TimeField()
    created_date = models.DateField(default=date.today)
    progress = models.IntegerField(default=0)
    total_so_far = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    helmet_given = models.BooleanField(default=False)  # New field
    key_given = models.BooleanField(default=False)    # New field
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.order_no} - {self.client_garage.name}"
    
    
    

class Bill(models.Model):
    STATUS_CHOICES = (
        ('Pending', 'Pending'),
        ('Generated (In Progress)', 'Generated (In Progress)'),
        ('Completed', 'Completed'),
        ('Credit', 'Credit'),
    )
    client_garage = models.ForeignKey('ClientGarage', on_delete=models.CASCADE, related_name='bills')
    bill_no = models.CharField(max_length=10, unique=True)
    service_order = models.ForeignKey('ServiceOrder', on_delete=models.CASCADE, null=True, blank=True)
    discount_type = models.CharField(max_length=20, default='percentage')
    discount_value = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    customer = models.ForeignKey('Customer', on_delete=models.SET_NULL, null=True, blank=True)
    vehicle = models.ForeignKey('Vehicle', on_delete=models.CASCADE, null=True, blank=True)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='Pending')
    items = models.JSONField(default=list)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    tax = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    credit_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    payment_mode = models.CharField(max_length=20, default='cash')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.bill_no} - {self.client_garage.name}"

class Part(models.Model):
    client_garage = models.ForeignKey('ClientGarage', on_delete=models.CASCADE, related_name='parts')
    client_fiscal_year = models.ForeignKey('ClientFiscalYear', on_delete=models.SET_NULL, null=True, blank=True)
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    category = models.ForeignKey('PartCategory', on_delete=models.CASCADE)
    vehicle_company = models.ForeignKey('VehicleCompany', on_delete=models.SET_NULL, null=True, blank=True)
    vehicle_type = models.ForeignKey('VehicleType', on_delete=models.SET_NULL, null=True, blank=True)
    vehicle_model = models.ForeignKey('VehicleModel', on_delete=models.SET_NULL, null=True, blank=True)
    supplier = models.ForeignKey('Supplier', on_delete=models.SET_NULL, null=True, blank=True)
    purchase_price = models.DecimalField(max_digits=10, decimal_places=2)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2)
    in_stock = models.PositiveIntegerField(default=0)
    min_stock = models.PositiveIntegerField(default=5)
    image = models.ImageField(upload_to='part_images/', blank=True, null=True)
    status = models.CharField(max_length=20, choices=[
        ('in-stock', 'In Stock'),
        ('low-stock', 'Low Stock'),
        ('out-of-stock', 'Out of Stock')
    ], default='in-stock')
    last_movement = models.DateField(default=date.today)
    movement_type = models.CharField(max_length=20, choices=[
        ('added', 'Added'),
        ('sold', 'Sold'),
        ('used', 'Used')
    ], default='added')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} - {self.client_garage.name}"


class Supplier(models.Model):
    client_garage = models.ForeignKey('ClientGarage', on_delete=models.CASCADE, related_name='suppliers')
    client_fiscal_year = models.ForeignKey('ClientFiscalYear', on_delete=models.SET_NULL, null=True, blank=True)
    name = models.CharField(max_length=100)
    contact_person = models.CharField(max_length=100, blank=True, null=True)
    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    vat_number = models.CharField(max_length=50, blank=True, null=True)
    category = models.CharField(max_length=100, choices=[
        ('lubricants', 'Lubricants'),
        ('spare-parts', 'Spare Parts'),
        ('drive-train', 'Drive Train'),
        ('electrical', 'Electrical'),
        ('tools', 'Tools & Equipment')
    ])
    credit_limit = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    current_credit = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    payment_terms = models.CharField(max_length=20, choices=[
        ('immediate', 'Immediate'),
        ('7-days', '7 Days'),
        ('15-days', '15 Days'),
        ('30-days', '30 Days'),
        ('45-days', '45 Days'),
        ('60-days', '60 Days')
    ], default='30-days')
    status = models.CharField(max_length=20, choices=[('active', 'Active'), ('inactive', 'Inactive')], default='active')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} - {self.client_garage.name}"

class PurchaseOrder(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('partially_paid', 'Partially Paid'),
    )
    client_garage = models.ForeignKey('ClientGarage', on_delete=models.CASCADE, related_name='purchase_orders')
    client_fiscal_year = models.ForeignKey('ClientFiscalYear', on_delete=models.SET_NULL, null=True, blank=True)
    supplier = models.ForeignKey('Supplier', on_delete=models.CASCADE, related_name='purchase_orders')
    purchase_no = models.CharField(max_length=20, unique=True)
    date = models.DateField(default=date.today)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    tax = models.DecimalField(max_digits=10, decimal_places=2)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    payment_mode = models.CharField(max_length=20, choices=[
        ('cash', 'Cash Payment'),
        ('credit', 'Credit Purchase'),
        ('advance', 'Advance Payment')
    ])
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    due_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.purchase_no} - {self.client_garage.name}"

class PurchaseOrderItem(models.Model):
    purchase_order = models.ForeignKey('PurchaseOrder', on_delete=models.CASCADE, related_name='items')
    part = models.ForeignKey('Part', on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    rate = models.DecimalField(max_digits=10, decimal_places=2)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.part.name} - {self.purchase_order.purchase_no}"

class SupplierPayment(models.Model):
    client_garage = models.ForeignKey('ClientGarage', on_delete=models.CASCADE, related_name='supplier_payments')
    supplier = models.ForeignKey('Supplier', on_delete=models.CASCADE, related_name='payments')
    purchase_order = models.ForeignKey('PurchaseOrder', on_delete=models.CASCADE, null=True, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_date = models.DateField(default=date.today)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Payment {self.id} - {self.supplier.name}"

class Item(models.Model):
    client_garage = models.ForeignKey('ClientGarage', on_delete=models.CASCADE, related_name="items")
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    category = models.CharField(max_length=50)
    stock = models.PositiveIntegerField(default=0)
    image = models.CharField(max_length=50, default="fa-motorcycle")  # FontAwesome class
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.code})"

class BillItem(models.Model):
    bill = models.ForeignKey('Bill', related_name='bill_items', on_delete=models.CASCADE)
    item = models.ForeignKey('Part', on_delete=models.SET_NULL, null=True, blank=True)
    service_type = models.ForeignKey('ServiceType', on_delete=models.SET_NULL, null=True, blank=True)
    name = models.CharField(max_length=100)
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} - {self.quantity} units"

    def clean(self):
        if (self.item is None and self.service_type is None) or (self.item is not None and self.service_type is not None):
            raise ValidationError("Exactly one of 'item' or 'service_type' must be set.")

    def save(self, *args, **kwargs):
        self.full_clean()  # Run validation before saving
        super().save(*args, **kwargs)
                

# garage/models.py
from django.db import models
class ServiceOrderItem(models.Model):
    service_order = models.ForeignKey(ServiceOrder, related_name='service_items', on_delete=models.CASCADE)
    service_type = models.ForeignKey('ServiceType', on_delete=models.CASCADE)
    price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        db_table = 'garage_serviceorderitem'

class StaffPayroll(models.Model):
    PAYMENT_MODES = (
        ('cash', 'Cash'),
        ('bank', 'Bank Transfer'),
        ('mobile', 'Mobile Payment'),
    )
    user = models.ForeignKey('User', on_delete=models.CASCADE, related_name='payrolls')
    client_garage = models.ForeignKey('ClientGarage', on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_date = models.DateField(default=date.today)
    payment_mode = models.CharField(max_length=20, choices=PAYMENT_MODES, default='cash')
    notes = models.TextField(blank=True, null=True)
    incentives = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Payroll {self.id} - {self.user.username}"

class StaffAttendance(models.Model):
    user = models.ForeignKey('User', on_delete=models.CASCADE, related_name='attendances')
    client_garage = models.ForeignKey('ClientGarage', on_delete=models.CASCADE)
    date = models.DateField(default=date.today)
    check_in = models.DateTimeField(null=True, blank=True)
    check_out = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=[
        ('present', 'Present'),
        ('absent', 'Absent'),
        ('leave', 'Leave'),
    ], default='present')
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'date')

    def __str__(self):
        return f"{self.user.username} - {self.date}"
