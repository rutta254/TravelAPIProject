# travel_api/locations/urls.py

from django.urls import path
from .views import CalculateDistanceView

urlpatterns = [
    path('calculate-distance/', CalculateDistanceView.as_view(), name='calculate_distance'),
]