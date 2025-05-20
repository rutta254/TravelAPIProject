# Django Travel Route & Optimal Fuel Stops API

This project provides a Django REST API that calculates optimal driving routes between two US locations and suggests cost-effective fuel stops along the way, considering vehicle range and fuel efficiency.

## Features

* **Route Calculation:** Integrates with OpenRouteService (ORS) API to determine distance, duration, and route geometry between given start and finish locations.
* **Optimal Fuel Stop Planning:** Identifies strategic fuel stops along the route based on:
    * Vehicle's maximum range (500 miles).
    * Vehicle's fuel efficiency (10 MPG).
    * Cost-effectiveness, utilizing provided fuel price data.
    * Maximum deviation from the route (10 miles).
* **Total Fuel Cost Estimation:** Calculates the estimated total fuel cost for the entire trip.
* **Geocoding:** Uses Nominatim for converting location names to coordinates.
* **Performance Optimization:**
    * Fuel station data is loaded and geocoded only once on server startup.
    * Geocoded fuel station data is cached (`.pkl` file) to prevent repeated geocoding on subsequent server restarts.
    * A KD-Tree is used for efficient spatial querying of nearby fuel stations.

## Technologies Used

* **Django 3.2.23:** Web framework
* **Django REST Framework:** For building the API.
* **Python 3.x:** Programming language
* **`geopy`:** For geocoding (Nominatim) and geodesic distance calculations.
* **`requests`:** For making HTTP requests to external APIs (OpenRouteService).
* **`polyline`:** For encoding/decoding route polylines.
* **`pandas`:** For data manipulation (reading CSV, handling fuel station data).
* **`scipy.spatial.KDTree`:** For optimized nearest-neighbor searches of fuel stations.

## Setup Instructions

Follow these steps to get the project up and running on your local machine.

### 1. Clone the Repository

```bash
git clone [https://github.com/rutta254/TravelAPIProject.git](https://github.com/rutta254/TravelAPIProject.git)
cd TravelAPIProject