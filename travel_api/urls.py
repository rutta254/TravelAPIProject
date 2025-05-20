# travel_api/travel_api/urls.py

from django.contrib import admin
from django.urls import path, include # <--- Make sure 'include' is here

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('locations.urls')), # <--- Make sure this line is EXACTLY correct
]