from django.urls import path
from . import views
from garage.view.admin.add_vehicle_view import add_vehicle, assign_mechanic, get_service_orders, add_vehicle_and_order, get_vehicle_models,search_vehicle,search_customer, staff_list, update_service_order, get_service_order
from garage.view.admin.pos_billing_view import pos_billing, get_tax_settings, get_daily_summary, generate_bill_pdf
from garage.view.admin.inventory_management import inventory_management, get_vehicle_models_a, get_vehicle_types_a, get_vehicle_companies, search_items, save_inventory, get_inventory, make_supplier_payment,create_purchase_order,save_supplier, get_purchase_orders, get_suppliers, get_tax_settings, upload_part_image, get_supplier_details
from garage.view.admin.staff_management_views import staff_management, get_attendance, generate_payroll_statement, get_payroll, save_payroll, delete_staff, save_staff, get_staff_list, save_attendance, toggle_attendance, get_payroll_excel_data
from garage.view.admin.admin_report_views import admin_report_views
from garage.view.admin.admin_setting import admin_setting_views, save_general_settings, save_fiscal_year,delete_fiscal_year, save_service_type,  save_user, delete_role, save_role, delete_part_category, save_part_category, delete_service_type,save_service_type,delete_fiscal_year,save_fiscal_year,save_general_settings, save_tax_settings, save_other_settings
from garage.view.admin.upload import admin_upload, download_template,upload_models,upload_vehicle_types,upload_companies, export_models,export_vehicle_types, export_companies, delete_models,delete_vehicle_types, delete_companies,save_models,save_vehicle_types,save_companies, get_model,get_vehicle_type,get_company,get_company,get_models, get_vehicle_types, get_companies
from garage.view.admin.pos_billing_view import generate_bill,save_bill, save_customer, get_bills, get_items, get_item, get_bill
from garage.view.admin.dashboard_view import dashboard_view



urlpatterns = [
    path('get-csrf-token/', views.get_csrf_token, name='get_csrf_token'),
    path('login/', views.LoginView.as_view(), name='login'),
    path('logout/', views.LogoutView.as_view(), name='logout'),
    path('superuser/dashboard/', views.superuser_dashboard, name='superuser_dashboard'),
    path('admin/dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('staff/dashboard/', views.staff_dashboard, name='staff_dashboard'),
    path('superuser/add-user/', views.add_company_user, name='add_company_user'),
    path('superuser/settings/', views.superuser_setting, name='superuser_setting'),
    path('superuser/save-financial-year/', views.save_financial_year, name='save_financial_year'),
    path('superuser/change-password/', views.change_password, name='change_password'),
    path('superuser/update-software-info/', views.update_software_info, name='update_software_info'),
    path('superuser/toggle-financial-year-status/', views.toggle_financial_year_status, name='toggle_financial_year_status'),
    path('superuser/edit-client-company/', views.edit_client_company, name='edit_client_company'),
    path('superuser/toggle-client-user-status/', views.toggle_client_user_status, name='toggle_client_user_status'),
    path('superuser/reset-client-password/', views.reset_client_password, name='reset_client_password'),

    path('admin/add-vehicle/', add_vehicle, name='add_vehicle'),
    path('admin/pos-billing/', pos_billing, name='pos_billing'),
    path('admin/inventory-management/', inventory_management, name='inventory_management'),
    path('admin/staff-management/', staff_management, name='staff_management'),
    path('admin/admin-report/', admin_report_views, name='admin_report'),
    path('admin/admin-setting/',admin_setting_views, name='admin_setting'),
    path('admin/admin-upload/', admin_upload, name='admin_upload'),

      # New paths for admin settings
    path('admin/save-general-settings/', save_general_settings, name='save_general_settings'),
    path('admin/save-fiscal-year/', save_fiscal_year, name='save_fiscal_year'),
    path('admin/delete-fiscal-year/', delete_fiscal_year, name='delete_fiscal_year'),
    path('admin/save-service-type/', save_service_type, name='save_service_type'),
    path('admin/delete-service-type/', delete_service_type, name='delete_service_type'),
    path('admin/save-part-category/', save_part_category, name='save_part_category'),
    path('admin/delete-part-category/', delete_part_category, name='delete_part_category'),
    path('admin/save-role/', save_role, name='save_role'),
    path('admin/delete-role/', delete_role, name='delete_role'),
    path('admin/save-user/', save_user, name='save_user'),
    path('admin/save-tax-settings/', save_tax_settings, name='save_tax_settings'),
    path('admin/save-other-settings/', save_other_settings, name='save_other_settings'),

    path('admin/get-companies/', get_companies, name='get_companies'),
    path('admin/get-vehicle-types/', get_vehicle_types, name='get_vehicle_types'),
    path('admin/get-models/', get_models, name='get_models'),
    path('admin/get-companies/<int:id>/', get_company, name='get_company'),
    path('admin/get-vehicle-types/<int:id>/', get_vehicle_type, name='get_vehicle_type'),
    path('admin/get-models/<int:id>/', get_model, name='get_model'),
    path('admin/save-companies/', save_companies, name='save_companies'),
    path('admin/save-companies/<int:id>/', save_companies, name='save_companies'),
    path('admin/save-vehicle-types/', save_vehicle_types, name='save_vehicle_types'),
    path('admin/save-vehicle-types/<int:id>/', save_vehicle_types, name='save_vehicle_types'),
    path('admin/save-models/', save_models, name='save_models'),
    path('admin/save-models/<int:id>/', save_models, name='save_models'),
    path('admin/delete-companies/<int:id>/', delete_companies, name='delete_companies'),
    path('admin/delete-vehicle-types/<int:id>/', delete_vehicle_types, name='delete_vehicle_types'),
    path('admin/delete-models/<int:id>/', delete_models, name='delete_models'),
    path('admin/export-companies/', export_companies, name='export_companies'),
    path('admin/export-vehicle-types/', export_vehicle_types, name='export_vehicle_types'),
    path('admin/export-models/', export_models, name='export_models'),
    path('admin/upload-companies/', upload_companies, name='upload_companies'),
    path('admin/upload-vehicle-types/', upload_vehicle_types, name='upload_vehicle_types'),
    path('admin/upload-models/', upload_models, name='upload_models'),
    path('admin/download-template/<str:type>/', download_template, name='download_template'),

    path('admin/search-customer/', search_customer, name='search_customer'),
    path('admin/search-vehicle/', search_vehicle, name='search_vehicle'),
    path('admin/get-vehicle-models/', get_vehicle_models, name='get_vehicle_models'),
    path('admin/add-vehicle-and-order/', add_vehicle_and_order, name='add_vehicle_and_order'),
    path('admin/get-service-orders/', get_service_orders, name='get_service_orders'),
    path('admin/assign-mechanic/', assign_mechanic, name='assign_mechanic'),
    path('admin/staff-list/', staff_list, name='staff_list'),
    path('admin/get-service-order/', get_service_order, name='get_service_order'),
    path('admin/update-service-order/', update_service_order, name='update_service_order'),

    path('admin/get-suppliers/', get_suppliers, name='get_suppliers'),
    path('admin/save-supplier/', save_supplier, name='save_supplier'),
    path('admin/get-purchase-orders/', get_purchase_orders, name='get_purchase_orders'),
    path('admin/create-purchase-order/', create_purchase_order, name='create_purchase_order'),
    path('admin/make-supplier-payment/', make_supplier_payment, name='make_supplier_payment'),
    path('admin/get-inventory/', get_inventory, name='get_inventory'),
    path('admin/save-inventory/', save_inventory, name='save_inventory'),
    path('admin/search-items/', search_items, name='search_items'),
    path('admin/get-vehicle-companies/', get_vehicle_companies, name='get_vehicle_companies'),
    path('admin/get-vehicle-types_a/', get_vehicle_types_a, name='get_vehicle_types_a'),
    path('admin/get-vehicle-models_a/', get_vehicle_models_a, name='get_vehicle_models_a'),
    path('admin/get-tax-settings/', get_tax_settings, name='get_tax_settings'),  # Added path

    # New POS URLs
    path('pos/', pos_billing, name='pos_billing'),
    path('pos/get_items/', get_items, name='get_items'),
    path('pos/get_item/', get_item, name='get_item'),
    path('pos/get_bills/', get_bills, name='get_bills'),
    path('pos/get_bill/', get_bill, name='get_bill'),
    path('pos/save_customer/', save_customer, name='save_customer'),
    path('pos/save_bill/', save_bill, name='save_bill'),
    path('pos/generate_bill/',generate_bill, name='generate_bill'),
    path('pos/generate_bill_pdf/', generate_bill_pdf, name='generate_bill_pdf'), 

    path('admin/get-staff-list/', get_staff_list, name='get_staff_list'),
    path('admin/save-staff/', save_staff, name='save_staff'),
    path('admin/delete-staff/', delete_staff, name='delete_staff'),
    path('admin/save-payroll/', save_payroll, name='save_payroll'),
    path('admin/get-payroll/', get_payroll, name='get_payroll'),
    path('admin/generate-payroll-statement/', generate_payroll_statement, name='generate_payroll_statement'),
    path('admin/save-attendance/', save_attendance, name='save_attendance'),
    path('admin/get-attendance/', get_attendance, name='get_attendance'),
    path('admin/toggle-attendance/',toggle_attendance, name='toggle_attendance'),
    path('admin/get-payroll-excel-data/', get_payroll_excel_data, name='get_payroll_excel_data'),

    path('admin/upload-part-image/', upload_part_image, name='upload_part_image'),
    path('admin/get_tax_settings/', get_tax_settings, name='get_tax_settings'),
    path('admin/get_daily_summary/', get_daily_summary, name='get_daily_summary'),
    path('admin/get-supplier-details/<int:supplier_id>/', get_supplier_details, name='get_supplier_details'),
    
]