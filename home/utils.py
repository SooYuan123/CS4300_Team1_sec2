import os
import base64
import requests
from dotenv import load_dotenv
from datetime import datetime, timedelta
from requests.exceptions import HTTPError
from django.conf import settings 

load_dotenv()
ASTRONOMY_API_BASE = "https://api.astronomyapi.com/api/v2/bodies/events"


def get_auth_header():
    app_id = getattr(settings, "ASTRONOMY_API_APP_ID", None) or os.getenv("ASTRONOMY_API_APP_ID")
    app_secret = getattr(settings, "ASTRONOMY_API_APP_SECRET", None) or os.getenv("ASTRONOMY_API_APP_SECRET")
    token = base64.b64encode(f"{app_id}:{app_secret}".encode()).decode()
    return {"Authorization": f"Basic {token}"}

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
