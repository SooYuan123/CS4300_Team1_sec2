import os
import base64
import requests
from dotenv import load_dotenv
from datetime import datetime, timedelta

load_dotenv()

ASTRONOMY_API_BASE = "https://api.astronomyapi.com/api/v2/bodies/events"
ASTRONOMY_API_APP_ID = os.getenv("ASTRONOMY_API_APP_ID")
ASTRONOMY_API_APP_SECRET = os.getenv("ASTRONOMY_API_APP_SECRET")

def get_auth_header():
    auth_string = base64.b64encode(f"{ASTRONOMY_API_APP_ID}:{ASTRONOMY_API_APP_SECRET}".encode()).decode()
    return {"Authorization": f"Basic {auth_string}"}

def fetch_astronomical_events(body, latitude, longitude, elevation=0, from_date=None, to_date=None):
    today = datetime.utcnow().date()
    
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

