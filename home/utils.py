import os
import base64
import requests
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
from requests.exceptions import HTTPError
from django.conf import settings

load_dotenv()

# API Configuration
ASTRONOMY_API_BASE = "https://api.astronomyapi.com/api/v2/bodies/events"
OPEN_METEO_API_BASE = "https://api.open-meteo.com/v1/forecast"
AMS_METEORS_API_BASE = "https://www.amsmeteors.org/members/api/open_api"

ASTRONOMY_API_APP_ID = os.getenv("ASTRONOMY_API_APP_ID")
ASTRONOMY_API_APP_SECRET = os.getenv("ASTRONOMY_API_APP_SECRET")
AMS_METEORS_API_KEY = getattr(settings, 'AMS_METEORS_API_KEY', '')

def get_auth_header():
    auth_string = base64.b64encode(f"{ASTRONOMY_API_APP_ID}:{ASTRONOMY_API_APP_SECRET}".encode()).decode()
    return {"Authorization": f"Basic {auth_string}"}

def fetch_astronomical_events(body, latitude, longitude, elevation=0, from_date=None, to_date=None):
    """Fetch astronomical events from Astronomy API for celestial bodies"""
    today = datetime.now(timezone.utc).date()
    
    # Default window: past 365 days to next ~3 years
    if not to_date:
        to_date = today + timedelta(days=1095)  # ~3 years ahead
    if not from_date:
        from_date = today - timedelta(days=365)  # past year

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "elevation": elevation,
        "from_date": from_date,
        "to_date": to_date,
        "time": "00:00:00",
        "output": "rows"
    }
    params["from_date"] = str(from_date)
    params["to_date"] = str(to_date)

    response = requests.get(f"{ASTRONOMY_API_BASE}/{body}", headers=get_auth_header(), params=params)
    response.raise_for_status()
    return response.json()["data"]["rows"]


def fetch_twilight_events(latitude, longitude, from_date=None, to_date=None):
    """
    Fetch astronomical twilight events from Open-Meteo API
    
    Args:
        latitude (str): Latitude coordinate
        longitude (str): Longitude coordinate
        from_date (date): Start date for data range
        to_date (date): End date for data range
    
    Returns:
        list: Standardized event data for twilight events
    """
    try:
        today = datetime.now(timezone.utc).date()
        
        # Default window: past 365 days to next ~3 years
        if not to_date:
            to_date = today + timedelta(days=1095)
        if not from_date:
            from_date = today - timedelta(days=365)
        
        params = {
            "latitude": float(latitude),
            "longitude": float(longitude),
            "daily": "sunrise,sunset,astronomical_twilight_start,astronomical_twilight_end",
            "start_date": str(from_date),
            "end_date": str(to_date),
            "timezone": "auto"
        }
        
        response = requests.get(OPEN_METEO_API_BASE, params=params)
        response.raise_for_status()
        data = response.json()
        
        events = []
        daily_data = data.get("daily", {})
        times = daily_data.get("time", [])
        
        for i, date_str in enumerate(times):
            # Create twilight start event
            twilight_start = daily_data.get("astronomical_twilight_start", [])
            if i < len(twilight_start) and twilight_start[i]:
                events.append({
                    "body": "Sun",
                    "type": "Astronomical Twilight Start",
                    "peak": f"{date_str}T{twilight_start[i]}",
                    "rise": twilight_start[i],
                    "set": None,
                    "obscuration": None,
                    "highlights": {
                        "source": "open_meteo",
                        "category": "twilight",
                        "description": "Beginning of astronomical twilight - sky becomes dark enough for astronomical observations"
                    }
                })
            
            # Create twilight end event
            twilight_end = daily_data.get("astronomical_twilight_end", [])
            if i < len(twilight_end) and twilight_end[i]:
                events.append({
                    "body": "Sun",
                    "type": "Astronomical Twilight End",
                    "peak": f"{date_str}T{twilight_end[i]}",
                    "rise": twilight_end[i],
                    "set": None,
                    "obscuration": None,
                    "highlights": {
                        "source": "open_meteo",
                        "category": "twilight",
                        "description": "End of astronomical twilight - sky becomes too bright for astronomical observations"
                    }
                })
        
        return events
        
    except Exception as e:
        print(f"Error fetching twilight events: {e}")
        return []


def fetch_meteor_shower_events(from_date=None, to_date=None, api_key=None):
    """
    Fetch meteor shower events from AMS Meteors API
    
    Args:
        from_date (date): Start date for data range
        to_date (date): End date for data range
        api_key (str): AMS Meteors API key
    
    Returns:
        list: Standardized event data for meteor showers
    """
    if not api_key:
        print("AMS Meteors API key not provided, skipping meteor shower data")
        return []
    
    try:
        today = datetime.now(timezone.utc).date()
        
        # Default window: past 365 days to next ~3 years
        if not to_date:
            to_date = today + timedelta(days=1095)
        if not from_date:
            from_date = today - timedelta(days=365)
        
        params = {
            "api_key": api_key,
            "start_date": str(from_date),
            "end_date": str(to_date)
        }
        
        response = requests.get(f"{AMS_METEORS_API_BASE}/get_events", params=params)
        response.raise_for_status()
        data = response.json()
        
        events = []
        if data.get("status") == 200:
            meteor_events = data.get("result", [])
            for event in meteor_events:
                events.append({
                    "body": "Meteor Shower",
                    "type": event.get("name", "Meteor Shower"),
                    "peak": event.get("peak_date"),
                    "rise": None,
                    "set": None,
                    "obscuration": None,
                    "highlights": {
                        "source": "ams_meteors",
                        "category": "meteor_shower",
                        "description": event.get("description", ""),
                        "meteor_count": event.get("meteor_count", "Unknown"),
                        "visibility": event.get("visibility", "Unknown")
                    }
                })
        
        return events
        
    except Exception as e:
        print(f"Error fetching meteor shower events: {e}")
        return []


def fetch_fireball_events(from_date=None, to_date=None, api_key=None, latitude=None, longitude=None):
    """
    Fetch fireball sighting events from AMS Meteors API
    
    Args:
        from_date (date): Start date for data range
        to_date (date): End date for data range
        api_key (str): AMS Meteors API key
        latitude (str): Latitude for proximity filtering
        longitude (str): Longitude for proximity filtering
    
    Returns:
        list: Standardized event data for fireball sightings
    """
    if not api_key:
        print("AMS Meteors API key not provided, skipping fireball data")
        return []
    
    try:
        today = datetime.now(timezone.utc).date()
        
        # Default window: past 365 days to next ~3 years
        if not to_date:
            to_date = today + timedelta(days=1095)
        if not from_date:
            from_date = today - timedelta(days=365)
        
        params = {
            "api_key": api_key,
            "start_date": str(from_date),
            "end_date": str(to_date),
            "pending_only": 0  # Include confirmed reports
        }
        
        response = requests.get(f"{AMS_METEORS_API_BASE}/get_close_reports", params=params)
        response.raise_for_status()
        data = response.json()
        
        events = []
        if data.get("status") == 200:
            fireball_reports = data.get("result", [])
            for report in fireball_reports:
                events.append({
                    "body": "Fireball",
                    "type": "Fireball Sighting",
                    "peak": report.get("date"),
                    "rise": None,
                    "set": None,
                    "obscuration": None,
                    "highlights": {
                        "source": "ams_meteors",
                        "category": "fireball",
                        "description": f"Fireball sighting reported",
                        "location": f"{report.get('city', 'Unknown')}, {report.get('state', 'Unknown')}",
                        "brightness": report.get("brightness", "Unknown"),
                        "trajectory": report.get("trajectory", "Unknown")
                    }
                })
        
        return events
        
    except Exception as e:
        print(f"Error fetching fireball events: {e}")
        return []


def standardize_event_data(event_data, source_api):
    """
    Transform API responses into unified format
    
    Args:
        event_data (dict): Raw event data from API
        source_api (str): Source API identifier
    
    Returns:
        dict: Standardized event data
    """
    # This function can be extended to normalize data from different APIs
    # For now, we'll return the data as-is since each API function already
    # returns standardized format
    return event_data

