
import base64
import requests
from datetime import datetime, timedelta
from django.conf import settings
from requests.exceptions import HTTPError, ConnectionError, Timeout

ASTRONOMY_API_BASE = "https://api.astronomyapi.com/api/v2/bodies/events"

def get_auth_header():
    """Build and return the Astronomy API auth header using settings vars."""
    app_id = getattr(settings, "ASTRONOMY_API_APP_ID", "")
    app_secret = getattr(settings, "ASTRONOMY_API_APP_SECRET", "")

    if not app_id or not app_secret:
        raise RuntimeError("AstronomyAPI credentials are not set in environment variables.")

    auth_string = base64.b64encode(f"{app_id}:{app_secret}".encode()).decode()
    return {"Authorization": f"Basic {auth_string}", "Content-Type": "application/json"}

def fetch_astronomical_events(body, latitude, longitude, elevation=0, from_date=None, to_date=None):
    """
    Fetches astronomical events for a given celestial body.
    Default date range: today to +30 days to avoid 403 errors from huge ranges.
    """
    today = datetime.utcnow().date()

    if not from_date:
        from_date = today
    if not to_date:
        to_date = today + timedelta(days=30)

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "elevation": elevation,
        "from_date": str(from_date),
        "to_date": str(to_date),
        "time": "00:00:00",
        "output": "rows",
    }



    response = requests.get(f"{ASTRONOMY_API_BASE}/{body}", headers=get_auth_header(), params=params)
    if response.status_code == 404:
        return []
    response.raise_for_status()
    return response.json()["data"]["rows"]

def fetch_all_events(latitude, longitude):
    """Fetch events from all major celestial bodies and sort chronologically"""
    celestial_bodies = ["sun", "moon"]
    events_data = []

    for body in celestial_bodies:
        try:
            print(f"Fetching events for {body}...")
            rows = fetch_astronomical_events(body, latitude, longitude)
            print(f"Response rows for {body}: {rows}")

            for row in rows:
                for event in row.get("events", []):
                    data = {
                        "body": row["body"]["name"],
                        "type": event.get("type"),
                        "peak": event.get("eventHighlights", {}).get("peak", {}).get("date"),
                        "rise": event.get("rise"),
                        "set": event.get("set"),
                        "obscuration": event.get("extraInfo", {}).get("obscuration"),
                        "highlights": event.get("eventHighlights", {})
                    }
                    events_data.append(data)
        except Exception as e:
            print(f"Error fetching {body} events: {e}")

    print(f"Total events fetched: {len(events_data)}")
    # Sort by peak date, using datetime.max for events without peak dates
    events_data = sorted(events_data, key=lambda e: e["peak"] or datetime.max.isoformat())
    return events_data
