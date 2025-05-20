# travel_api/locations/serializers.py

from rest_framework import serializers

class LocationInputSerializer(serializers.Serializer):
    start_location = serializers.CharField(max_length=255)
    finish_location = serializers.CharField(max_length=255)

    def validate(self, data):
        # This is where you could add more complex validation
        # For now, we're just accepting the strings
        return data