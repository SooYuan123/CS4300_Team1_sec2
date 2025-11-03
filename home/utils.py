import os
import base64
import requests
from datetime import timezone
from dotenv import load_dotenv
from datetime import datetime, timedelta
from requests.exceptions import HTTPError
from django.conf import settings 

load_dotenv()
ASTRONOMY_API_BASE = "https://api.astronomyapi.com/api/v2/bodies/events"
SOLAR_SYSTEM_API_BASE = "https://api.le-systeme-solaire.net/rest/bodies"


def get_auth_header():
    app_id = getattr(settings, "ASTRONOMY_API_APP_ID", None) or os.getenv("ASTRONOMY_API_APP_ID")
    app_secret = getattr(settings, "ASTRONOMY_API_APP_SECRET", None) or os.getenv("ASTRONOMY_API_APP_SECRET")
    token = base64.b64encode(f"{app_id}:{app_secret}".encode()).decode()
    return {"Authorization": f"Basic {token}"}

def get_solar_system_auth_header():
    """Get authorization header for Solar System OpenData API"""
    api_key = getattr(settings, "SOLAR_SYSTEM_API_KEY", None) or os.getenv("SOLAR_SYSTEM_API_KEY")
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}

def fetch_astronomical_events(body, latitude, longitude, elevation=0, from_date=None, to_date=None):
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

    try:
        response = requests.get(f"{ASTRONOMY_API_BASE}/{body}", headers=get_auth_header(), params=params)
        if response.status_code == 404:
            return []  # graceful “not found”
        response.raise_for_status()
        return response.json()["data"]["rows"]
    except HTTPError as e:
        if getattr(e, "response", None) is not None and e.response is not None and e.response.status_code == 404:
            return []  # also accept 404 via raised path
        raise  # rethrow 403 and others for tests

def fetch_celestial_body_positions():
    """Fetch celestial body data from Solar System OpenData API."""
    celestial_bodies = ["sun","moon","mercury","venus","mars","jupiter","saturn","uranus","neptune"]

    positions = []

    for body in celestial_bodies:
        try:
            response = requests.get(f"{SOLAR_SYSTEM_API_BASE}/{body}", timeout=5)
            if response.status_code == 200:
                data = response.json()

                #Extract relevant information
                body_info = {
                    "name": data.get("englishName", body.capitalize()),
                    "id": data.get("id", body),
                    "mass": data.get("mass", {}),
                    "volume": data.get("vol", {}),
                    "density": data.get("density"),
                    "gravity": data.get("gravity"),
                    "meanRadius": data.get("meanRadius"),
                    "equaRadius": data.get("equaRadius"),
                    "polarRadius": data.get("polarRadius"),
                    "sideralOrbit": data.get("sideralOrbit"),
                    "sideralRotation": data.get("sideralRotation"),
                    "aroundPlanet": data.get("aroundPlanet"),
                    "discoveredBy": data.get("discoveredBy", "Known since antiquity"),
                    "discoveryDate": data.get("discoveryDate", ""),
                    "axialTilt": data.get("axialTilt"),
                    "avgTemp": data.get("avgTemp"),
                    "moons": data.get("moons", []),
                }
                positions.append(body_info)
        except Exception as e:
            print(f"Error fetching {body} data: {e}")
            continue

    return positions

def calculate_next_visibility(body_name, latitude=38.8339, longitude=-104.8214):
    """
    Calculate when a celestial body will next be visible.
    For now, uses simplified logic based on rise/set times fro astronomy API.

    Default Location: Colorado Springs, CO (38.8339°N, -104.8214°W)
    """
    try:
        rows = fetch_astronomical_events(body_name.lower(), latitude, longitude)
        if not rows:
            return None

        now = datetime.now(timezone.utc)

        for row in rows:
            rise_time = row.get("rise", {})
            if rise_time:
                rise_date_str = rise_time.get("date")
                if rise_date_str:
                    try:
                        rise_date = datetime.fromisoformat(rise_date_str.replace('Z', '+00:00'))
                        if rise_date > now:
                            return rise_date
                    except Exception:
                        continue
        return None
    except Exception as e:
        print(f"Error calculating visibility for {body_name}: {e}")
        return None

def get_celestial_bodies_with_visibility(latitude=38.8339, longitude=-104.8214):
    """
    Get celestial bodies with their positions and next visibility times.
    Sorted by next visibility time.

    Default Location: Colorado Springs, CO (38.8339°N, -104.8214°W)
    """
    positions = fetch_celestial_body_positions()

    # Add Visibility Information
    for body in positions:
        visibility = calculate_next_visibility(body["name"], latitude, longitude)
        body["nextVisible"] = visibility
        body["nextVisibleStr"] = visibility.isoformat() if visibility else None
    
    # Sort By Next Visibility (None Values go to the end)
    positions.sort(key=lambda x: x["nextVisible"] or datetime.max.replace(tzinfo=None))
    
    return positions