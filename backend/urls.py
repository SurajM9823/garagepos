from django.urls import path, include
from django.conf.urls.static import static
from django.conf import settings
from garage.views import login_page

urlpatterns = [
    path('', include('garage.urls')),
    path('', login_page, name='root'),  # Root renders login_page
]
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)