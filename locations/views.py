# travel_api/locations/views.py

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .serializers import LocationInputSerializer
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import requests
from django.conf import settings
import polyline
import pandas as pd
import os
from tqdm import tqdm
from scipy.spatial import KDTree
import numpy as np

# Global variables
_fuel_stations_df = None
_fuel_stations_kdtree = None
_geolocator_instance = None

def _load_and_geocode_fuel_stations():
    global _fuel_stations_df, _fuel_stations_kdtree, _geolocator_instance

    if _fuel_stations_df is not None and _fuel_stations_kdtree is not None:
        print("Fuel stations data and KD-Tree already loaded in this session. Skipping re-load.")
        return _fuel_stations_df # Data and KD-Tree already loaded

    fuel_prices_csv_path = os.path.join(settings.BASE_DIR, 'data', 'fuel_prices.csv')
    geocoded_cache_path = os.path.join(settings.BASE_DIR, 'data', 'geocoded_fuel_prices.pkl')

    df = None # Initialize df outside try block

    # --- Try to load from cache first ---
    if os.path.exists(geocoded_cache_path):
        print(f"Loading fuel stations from cached file: {geocoded_cache_path}...")
        try:
            df = pd.read_pickle(geocoded_cache_path)
            print(f"Successfully loaded {df.shape[0]} fuel stations from cache.")
            # Ensure latitude/longitude are numeric and not NaN after loading from cache
            df['latitude'] = pd.to_numeric(df['latitude'], errors='coerce')
            df['longitude'] = pd.to_numeric(df['longitude'], errors='coerce')
            df.dropna(subset=['latitude', 'longitude'], inplace=True)
            _fuel_stations_df = df
        except Exception as e:
            print(f"Error loading cache file ({e}), attempting to re-geocode from original CSV.")
            df = None # Reset df to force re-geocoding

    # --- If cache not found or failed, proceed with original CSV geocoding ---
    if df is None: # If df is still None, means cache failed or didn't exist
        if not os.path.exists(fuel_prices_csv_path):
            print(f"Error: Original CSV file not found at {fuel_prices_csv_path}. Please ensure it is in travel_api/data/.")
            return None

        print("Loading and geocoding fuel stations from CSV (this will take a while for large files)...")
        df = pd.read_csv(fuel_prices_csv_path)

        if _geolocator_instance is None:
            _geolocator_instance = Nominatim(user_agent="travel_api_app_geocoder")

        df['latitude'] = None
        df['longitude'] = None

        for index, row in tqdm(df.iterrows(), total=df.shape[0], desc="Geocoding Stations"):
            address = str(row['Address']) if not pd.isna(row['Address']) else ''
            city = str(row['City']) if not pd.isna(row['City']) else ''
            state = str(row['State']) if not pd.isna(row['State']) else ''

            address_str = f"{address}, {city}, {state}, USA"
            try:
                location = _geolocator_instance.geocode(address_str, timeout=10)
                if location:
                    df.loc[index, 'latitude'] = location.latitude
                    df.loc[index, 'longitude'] = location.longitude
            except Exception as e:
                pass # Geocoding errors handled by checking for None below

        df['latitude'] = pd.to_numeric(df['latitude'], errors='coerce') # Ensure numeric
        df['longitude'] = pd.to_numeric(df['longitude'], errors='coerce') # Ensure numeric
        df.dropna(subset=['latitude', 'longitude'], inplace=True) # Drop rows that couldn't be geocoded

        # --- Save the geocoded DataFrame to cache ---
        try:
            df.to_pickle(geocoded_cache_path)
            print(f"Geocoded data saved to cache: {geocoded_cache_path}")
        except Exception as e:
            print(f"Warning: Could not save geocoded data to cache: {e}")

        _fuel_stations_df = df
        print(f"Finished geocoding. Loaded {_fuel_stations_df.shape[0]} usable fuel stations.")

    # --- Build KD-Tree from the geocoded data ---
    if _fuel_stations_df is not None and not _fuel_stations_df.empty:
        # Create a numpy array of (latitude, longitude) for the KDTree
        points = _fuel_stations_df[['latitude', 'longitude']].values
        _fuel_stations_kdtree = KDTree(points)
        print("KD-Tree built for fuel stations.")
    else:
        print("No usable fuel station data to build KD-Tree.")
        _fuel_stations_kdtree = None # Ensure it's None if no data

    return _fuel_stations_df

class CalculateDistanceView(APIView):
    serializer_class = LocationInputSerializer

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid():
            start_location_str = serializer.validated_data['start_location']
            finish_location_str = serializer.validated_data['finish_location']

            geolocator = Nominatim(user_agent="travel_api_app_request_geocoder")
            ors_api_key = settings.ORS_API_KEY

            if not ors_api_key or ors_api_key == 'YOUR_ORS_API_KEY_HERE':
                return Response(
                    {"error": "OpenRouteService API key not configured. Please add it to settings.py."},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

            # Access the globally loaded DataFrame and KD-Tree
            global _fuel_stations_df, _fuel_stations_kdtree
            fuel_stations_data = _fuel_stations_df
            fuel_stations_kdtree = _fuel_stations_kdtree

            if fuel_stations_data is None or fuel_stations_data.empty or fuel_stations_kdtree is None:
                return Response(
                    {"error": "Fuel prices data not loaded or KD-Tree not built. This usually happens if the CSV path is wrong or geocoding failed for all entries during server startup. Check your server's console for details."},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

            try:
                # 1. Geocode start and finish locations (user input)
                start_location = geolocator.geocode(start_location_str + ", USA")
                finish_location = geolocator.geocode(finish_location_str + ", USA")

                if not start_location or not finish_location:
                    return Response(
                        {"error": "Could not find one or both route locations. Please be more specific or check spelling."},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                start_coords_lonlat = [start_location.longitude, start_location.latitude]
                finish_coords_lonlat = [finish_location.longitude, finish_location.latitude]

                # 2. Call OpenRouteService Directions API for route
                ors_directions_url = "https://api.openrouteservice.org/v2/directions/driving-car"
                headers = {
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "Authorization": ors_api_key
                }
                body = {
                    "coordinates": [start_coords_lonlat, finish_coords_lonlat],
                    "units": "mi",
                    "preference": "fastest",
                    "format": "json",
                    "options": {
                        "avoid_features": ["ferries"]
                    }
                }

                ors_response = requests.post(ors_directions_url, json=body, headers=headers)
                ors_response.raise_for_status()
                ors_data = ors_response.json()

                # Extract route details
                route_summary = ors_data['routes'][0]['summary']
                total_distance_miles = route_summary['distance']
                duration_seconds = route_summary['duration']
                encoded_polyline = ors_data['routes'][0]['geometry']

                # Decode the polyline to get a list of (lat, lon) coordinates
                decoded_route_points = polyline.decode(encoded_polyline)

                # --- 3. Multiple Fuel Stop Planning ---
                max_vehicle_range_miles = 500 # miles
                vehicle_mpg = 10 # miles per gallon
                tank_capacity_gallons = max_vehicle_range_miles / vehicle_mpg # 50 gallons

                refuel_threshold_miles = 200 # miles (start looking for fuel when range drops below this)
                max_deviation_from_route_miles = 10 # Max distance a station can be from the route to be considered

                current_range_miles = max_vehicle_range_miles # Start with full tank
                distance_traveled_on_route = 0

                optimal_fuel_stops_list = []
                total_fuel_cost = 0.0 # New variable to track total cost

                if len(decoded_route_points) < 2:
                    return Response({"error": "Route is too short to plan fuel stops."}, status=status.HTTP_400_BAD_REQUEST)

                # We iterate through segments of the route, not just points
                for i in range(len(decoded_route_points) - 1):
                    segment_start_coords = decoded_route_points[i]
                    segment_end_coords = decoded_route_points[i + 1]

                    # Calculate distance of this route segment
                    segment_distance = geodesic(segment_start_coords, segment_end_coords).miles

                    # Simplified trigger: If remaining range drops below threshold, or if this segment itself exceeds range
                    if current_range_miles <= refuel_threshold_miles or current_range_miles < segment_distance:

                        # Search for fuel stations around the current segment_start_coords
                        search_point = segment_start_coords

                        # Approximate degrees for 10 miles. Used for initial KDTree radius search.
                        approx_degree_radius = max_deviation_from_route_miles / 69.0 # ~69 miles per degree latitude

                        # Query KDTree for nearby stations (indices)
                        indices_nearby = fuel_stations_kdtree.query_ball_point(search_point, r=approx_degree_radius)

                        nearby_stations = []
                        for idx in indices_nearby:
                            station = fuel_stations_data.iloc[idx] # This returns a Series object

                            station_lat = station['latitude'] # Access by column name
                            station_lon = station['longitude'] # Access by column name

                            # Ensure latitude and longitude are valid numbers
                            if pd.isna(station_lat) or pd.isna(station_lon):
                                continue # Skip stations that couldn't be geocoded or have NaN coordinates

                            station_coords = (station_lat, station_lon)

                            # Re-check precise geodesic distance to the search point
                            actual_dist_to_route_point = geodesic(search_point, station_coords).miles

                            if actual_dist_to_route_point <= max_deviation_from_route_miles:
                                # Access columns by their exact string names as they appear in the CSV header
                                price = station['Retail Price'] # CORRECTED ACCESS

                                if not pd.isna(price): # Ensure price is not NaN
                                    nearby_stations.append({
                                        'name': station['Truckstop Name'], # CORRECTED ACCESS
                                        'address': f"{station['Address']}, {station['City']}, {station['State']}", # CORRECTED ACCESS
                                        'coordinates': {'latitude': station.latitude, 'longitude': station.longitude},
                                        'price_per_gallon': round(float(price), 2),
                                        'distance_off_route_miles': round(actual_dist_to_route_point, 2)
                                    })

                        # Sort nearby stations by price to pick the cheapest
                        nearby_stations.sort(key=lambda x: x['price_per_gallon'])

                        if nearby_stations:
                            chosen_stop = nearby_stations[0]
                            optimal_fuel_stops_list.append({
                                'stop_number': len(optimal_fuel_stops_list) + 1,
                                'location': chosen_stop,
                                'distance_into_route_miles': round(distance_traveled_on_route, 2)
                            })
                            # Refuel: add cost and reset range
                            total_fuel_cost += (chosen_stop['price_per_gallon'] * tank_capacity_gallons)
                            current_range_miles = max_vehicle_range_miles
                        else:
                            # This warning means no fuel station was found when needed.
                            print(f"Warning: No suitable fuel station found near {round(distance_traveled_on_route,2)} miles into route.")

                    # Drive this segment
                    current_range_miles -= segment_distance
                    distance_traveled_on_route += segment_distance

                # Final check: If total_distance_miles is very small and no stops were needed, but we start with full tank.
                # Or if no stops were found throughout.
                if not optimal_fuel_stops_list and total_distance_miles > 0:
                    gallons_for_full_trip = total_distance_miles / vehicle_mpg
                    # A more sophisticated approach might calculate cost based on an initial price if no stops are made.
                    # For this scenario, if no stops were needed/found, total_fuel_cost remains 0.0.
                    pass # Keep this pass statement as it's from your original code.


                response_data = {
                    'start_location': start_location_str,
                    'finish_location': finish_location_str,
                    'start_coordinates': {'latitude': round(start_location.latitude, 6), 'longitude': round(start_location.longitude, 6)},
                    'finish_coordinates': {'latitude': round(finish_location.latitude, 6), 'longitude': round(finish_location.longitude, 6)},
                    'total_distance_miles': round(total_distance_miles, 2),
                    'duration_seconds': round(duration_seconds, 2),
                    'vehicle_mpg': vehicle_mpg,
                    'vehicle_max_range_miles': max_vehicle_range_miles,
                    'estimated_total_fuel_cost': round(total_fuel_cost, 2),
                    'optimal_fuel_stops': optimal_fuel_stops_list,
                    'encoded_route_polyline': encoded_polyline,
                    'message': 'Route and optimal fuel stops calculated successfully.'
                }
                return Response(response_data, status=status.HTTP_200_OK)

            except requests.exceptions.RequestException as e:
                return Response(
                    {"error": f"Error communicating with routing service: {str(e)}"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            except KeyError as e:
                return Response(
                    {"error": f"Unexpected response format from ORS API. Missing key: {e}. Check ORS API key or request payload."},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            except Exception as e:
                return Response(
                    {"error": f"An unexpected error occurred: {str(e)}"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)