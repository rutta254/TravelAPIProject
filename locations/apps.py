# travel_api/locations/apps.py

from django.apps import AppConfig

class LocationsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'locations'

    def ready(self):
        try:
            from .views import _load_and_geocode_fuel_stations
            _load_and_geocode_fuel_stations()
        except Exception as e:
            print(f"Error during initial fuel station geocoding: {e}")