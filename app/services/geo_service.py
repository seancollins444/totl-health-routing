"""
Geo-distance calculation service using Google Maps Geocoding API.
Falls back to mock calculation if API is unavailable.
"""
import os
import requests
from typing import Optional, Tuple
import math

# Simple in-memory cache for zip code coordinates
_zip_cache = {}

def get_coordinates(zip_code: str) -> Optional[Tuple[float, float]]:
    """
    Get latitude and longitude for a zip code using Google Maps Geocoding API.
    Returns (lat, lng) tuple or None if not found.
    Caches results to minimize API calls.
    """
    if not zip_code:
        return None
    
    # Check cache first
    if zip_code in _zip_cache:
        return _zip_cache[zip_code]
    
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        return None
    
    try:
        url = f"https://maps.googleapis.com/maps/api/geocode/json"
        params = {
            "address": zip_code,
            "key": api_key,
            "components": "country:US"  # Limit to US zip codes
        }
        
        response = requests.get(url, params=params, timeout=5)
        data = response.json()
        
        if data.get("status") == "OK" and data.get("results"):
            location = data["results"][0]["geometry"]["location"]
            coords = (location["lat"], location["lng"])
            _zip_cache[zip_code] = coords
            return coords
    except Exception as e:
        print(f"Geocoding API error for {zip_code}: {e}")
    
    return None

def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great circle distance in miles between two points 
    on the earth (specified in decimal degrees).
    """
    # Convert decimal degrees to radians
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    
    # Haversine formula
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    
    # Radius of earth in miles
    r = 3956
    
    return c * r

def calculate_distance_mock(zip1: str, zip2: str) -> float:
    """
    Mock distance calculation for fallback.
    Logic:
    - Same zip: 0 miles
    - First 3 digits match (same area): 5-10 miles
    - Different area: 15-30 miles
    """
    if not zip1 or not zip2:
        return 999
        
    if zip1 == zip2:
        return 0.0
        
    # First 3 digits match = same general area
    if zip1[:3] == zip2[:3]:
        diff = abs(int(zip1[-2:]) - int(zip2[-2:]))
        return min(5 + (diff / 10), 10)
    
    # Different areas
    diff = abs(int(zip1[:3]) - int(zip2[:3]))
    return min(15 + diff, 30)

def calculate_distance(zip1: str, zip2: str) -> float:
    """
    Calculate approximate distance between two zip codes in miles.
    Uses Google Maps Geocoding API if available, falls back to mock.
    
    Returns distance in miles.
    """
    # Try real geocoding first
    coords1 = get_coordinates(zip1)
    coords2 = get_coordinates(zip2)
    
    if coords1 and coords2:
        distance = haversine_distance(coords1[0], coords1[1], coords2[0], coords2[1])
        return round(distance, 1)
    
    # Fallback to mock calculation
    return calculate_distance_mock(zip1, zip2)
