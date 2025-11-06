import os
import base64
import requests
from datetime import datetime, timedelta, timezone
from requests.exceptions import HTTPError, RequestException
from django.conf import settings

ASTRONOMY_API_BASE = "https://api.astronomyapi.com/api/v2/bodies/events"
OPEN_METEO_API_BASE = "https://api.open-meteo.com/v1/forecast"
AMS_METEORS_API_BASE = "https://www.amsmeteors.org/members/api/open_api"

def get_auth_header():
    app_id = getattr(settings, "ASTRONOMY_API_APP_ID", None) or os.getenv("ASTRONOMY_API_APP_ID")
    app_secret = getattr(settings, "ASTRONOMY_API_APP_SECRET", None) or os.getenv("ASTRONOMY_API_APP_SECRET")
    if not app_id or not app_secret:
        return {}  # allow tests/CI without creds
    token = base64.b64encode(f"{app_id}:{app_secret}".encode()).decode()
    return {"Authorization": f"Basic {token}"}

def fetch_astronomical_events(body, latitude, longitude, elevation=0, from_date=None, to_date=None):
    """Return Astronomy API rows[] or [] (404 -> [], 403 -> raise)."""
    today = datetime.now(timezone.utc).date()
    to_date = to_date or (today + timedelta(days=1095))
    from_date = from_date or (today - timedelta(days=365))

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "elevation": elevation,
        "from_date": str(from_date),
        "to_date": str(to_date),
        "time": "00:00:00",
        "output": "rows",
    }

    try:
        resp = requests.get(f"{ASTRONOMY_API_BASE}/{body}", headers=get_auth_header(), params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json() or {}
        return ((data.get("data") or {}).get("rows")) or []
    except HTTPError as e:
        status = getattr(e.response, "status_code", None)
        if status == 404:
            return []
        if status == 403:
            raise
        print(f"HTTP error fetching {body}: {e}")
        return []
    except (RequestException, ValueError) as e:
        print(f"Error fetching AstronomyAPI {body}: {e}")
        return []

def fetch_twilight_events(latitude, longitude, from_date=None, to_date=None):
    """Open-Meteo: returns list of twilight events; logs and returns [] on error."""
    try:
        today = datetime.now(timezone.utc).date()
        to_date = to_date or (today + timedelta(days=1095))
        from_date = from_date or (today - timedelta(days=365))

        params = {
            "latitude": float(latitude),
            "longitude": float(longitude),
            "daily": "sunrise,sunset,astronomical_twilight_start,astronomical_twilight_end",
            "start_date": str(from_date),
            "end_date": str(to_date),
            "timezone": "auto",
        }
        r = requests.get(OPEN_METEO_API_BASE, params=params, timeout=15)
        r.raise_for_status()
        data = r.json() or {}
        daily = data.get("daily", {})
        times = daily.get("time", []) or []

        events = []
        tw_start = daily.get("astronomical_twilight_start", []) or []
        tw_end = daily.get("astronomical_twilight_end", []) or []

        for i, date_str in enumerate(times):
            if i < len(tw_start) and tw_start[i]:
                events.append({
                    "body": "Sun",
                    "type": "Astronomical Twilight Start",
                    "peak": f"{date_str}T{tw_start[i]}",
                    "rise": tw_start[i],
                    "set": None,
                    "obscuration": None,
                    "highlights": {"source": "open_meteo", "category": "twilight",
                                   "description": "Beginning of astronomical twilight"},
                })
            if i < len(tw_end) and tw_end[i]:
                events.append({
                    "body": "Sun",
                    "type": "Astronomical Twilight End",
                    "peak": f"{date_str}T{tw_end[i]}",
                    "rise": tw_end[i],
                    "set": None,
                    "obscuration": None,
                    "highlights": {"source": "open_meteo", "category": "twilight",
                                   "description": "End of astronomical twilight"},
                })
        return events
    except Exception as e:
        print(f"Error fetching twilight events: {e}")
        return []

def fetch_meteor_shower_events(from_date=None, to_date=None, api_key=None):
    """AMS meteors (optional): returns list; [] if no key or error."""
    if not api_key:
        print("AMS Meteors API key not provided, skipping meteor shower data")
        return []
    try:
        today = datetime.now(timezone.utc).date()
        to_date = to_date or (today + timedelta(days=1095))
        from_date = from_date or (today - timedelta(days=365))

        params = {"api_key": api_key, "start_date": str(from_date), "end_date": str(to_date)}
        r = requests.get(f"{AMS_METEORS_API_BASE}/get_events", params=params, timeout=15)
        r.raise_for_status()
        data = r.json() or {}

        events = []
        if data.get("status") == 200:
            for ev in data.get("result", []) or []:
                events.append({
                    "body": "Meteor Shower",
                    "type": ev.get("name", "Meteor Shower"),
                    "peak": ev.get("peak_date"),
                    "rise": None,
                    "set": None,
                    "obscuration": None,
                    "highlights": {
                        "source": "ams_meteors",
                        "category": "meteor_shower",
                        "description": ev.get("description", ""),
                        "meteor_count": ev.get("meteor_count", "Unknown"),
                        "visibility": ev.get("visibility", "Unknown"),
                    },
                })
        return events
    except Exception as e:
        print(f"Error fetching meteor shower events: {e}")
        return []

def fetch_fireball_events(from_date=None, to_date=None, api_key=None, latitude=None, longitude=None):
    """AMS fireballs (optional): returns list; [] if no key or error."""
    if not api_key:
        print("AMS Meteors API key not provided, skipping fireball data")
        return []
    try:
        today = datetime.now(timezone.utc).date()
        to_date = to_date or (today + timedelta(days=1095))
        from_date = from_date or (today - timedelta(days=365))

        params = {
            "api_key": api_key,
            "start_date": str(from_date),
            "end_date": str(to_date),
            "pending_only": 0,
        }
        r = requests.get(f"{AMS_METEORS_API_BASE}/get_close_reports", params=params, timeout=15)
        r.raise_for_status()
        data = r.json() or {}

        events = []
        if data.get("status") == 200:
            for rep in data.get("result", []) or []:
                events.append({
                    "body": "Fireball",
                    "type": "Fireball Sighting",
                    "peak": rep.get("date"),
                    "rise": None,
                    "set": None,
                    "obscuration": None,
                    "highlights": {
                        "source": "ams_meteors",
                        "category": "fireball",
                        "description": "Fireball sighting reported",
                        "location": f"{rep.get('city', 'Unknown')}, {rep.get('state', 'Unknown')}",
                        "brightness": rep.get("brightness", "Unknown"),
                        "trajectory": rep.get("trajectory", "Unknown"),
                    },
                })
        return events
    except Exception as e:
        print(f"Error fetching fireball events: {e}")
        return []
