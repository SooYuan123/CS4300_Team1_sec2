import os
import base64
import requests
from datetime import datetime, timedelta, timezone
from requests.exceptions import HTTPError, RequestException
from django.conf import settings

# If python-dotenv is present locally, this won't hurt; on CI/Render it's a no-op.
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    pass

# ---- API endpoints ----
ASTRONOMY_API_BASE = "https://api.astronomyapi.com/api/v2/bodies/events"
OPEN_METEO_API_BASE = "https://api.open-meteo.com/v1/forecast"
AMS_METEORS_API_BASE = "https://www.amsmeteors.org/members/api/open_api"

# ---- Config / defaults ----
HTTP_TIMEOUT = 15  # seconds

ASTRONOMY_API_APP_ID = getattr(settings, "ASTRONOMY_API_APP_ID", None) or os.getenv("ASTRONOMY_API_APP_ID")
ASTRONOMY_API_APP_SECRET = getattr(settings, "ASTRONOMY_API_APP_SECRET", None) or os.getenv("ASTRONOMY_API_APP_SECRET")
AMS_METEORS_API_KEY = getattr(settings, "AMS_METEORS_API_KEY", "") or os.getenv("AMS_METEORS_API_KEY", "")


def get_auth_header():
    """
    Build Basic auth header for Astronomy API, or return {} if creds are not set
    (CI/tests commonly run without them).
    """
    app_id = ASTRONOMY_API_APP_ID
    app_secret = ASTRONOMY_API_APP_SECRET
    if not app_id or not app_secret:
        return {}
    token = base64.b64encode(f"{app_id}:{app_secret}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def fetch_astronomical_events(body, latitude, longitude, elevation=0, from_date=None, to_date=None):
    """
    Fetch astronomical events for a given body from Astronomy API.

    Behavior expected by tests:
      - 404 -> return []
      - 403 -> re-raise (surface auth/permission issues)
      - other errors -> log and return []
    """
    today = datetime.now(timezone.utc).date()
    to_date = to_date or (today + timedelta(days=1095))  # ~3 years ahead
    from_date = from_date or (today - timedelta(days=365))  # ~1 year back

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
        resp = requests.get(
            f"{ASTRONOMY_API_BASE}/{body}",
            headers=get_auth_header(),
            params=params,
            timeout=HTTP_TIMEOUT,
        )
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
    """
    Fetch astronomical twilight events from Open-Meteo and return a standardized list.
    Logs and returns [] on error.
    """
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

        resp = requests.get(OPEN_METEO_API_BASE, params=params, timeout=HTTP_TIMEOUT)
        resp.raise_for_status()
        data = resp.json() or {}

        daily = data.get("daily") or {}
        times = daily.get("time") or []
        tw_start = daily.get("astronomical_twilight_start") or []
        tw_end = daily.get("astronomical_twilight_end") or []

        events = []
        for i, date_str in enumerate(times):
            if i < len(tw_start) and tw_start[i]:
                events.append({
                    "body": "Sun",
                    "type": "Astronomical Twilight Start",
                    "peak": f"{date_str}T{tw_start[i]}",
                    "rise": tw_start[i],
                    "set": None,
                    "obscuration": None,
                    "highlights": {
                        "source": "open_meteo",
                        "category": "twilight",
                        "description": "Beginning of astronomical twilight - sky becomes dark enough for observations",
                    },
                })
            if i < len(tw_end) and tw_end[i]:
                events.append({
                    "body": "Sun",
                    "type": "Astronomical Twilight End",
                    "peak": f"{date_str}T{tw_end[i]}",
                    "rise": tw_end[i],
                    "set": None,
                    "obscuration": None,
                    "highlights": {
                        "source": "open_meteo",
                        "category": "twilight",
                        "description": "End of astronomical twilight - sky becomes too bright for observations",
                    },
                })
        return events

    except (HTTPError, RequestException, ValueError) as e:
        print(f"Error fetching twilight events: {e}")
        return []


def fetch_meteor_shower_events(from_date=None, to_date=None, api_key=None):
    """
    Fetch meteor shower events from AMS Meteors API and return standardized events.
    If no key is provided/configured, returns [] (optional data source).
    """
    api_key = api_key or AMS_METEORS_API_KEY
    if not api_key:
        print("AMS Meteors API key not provided, skipping meteor shower data")
        return []
    try:
        today = datetime.now(timezone.utc).date()
        to_date = to_date or (today + timedelta(days=1095))
        from_date = from_date or (today - timedelta(days=365))

        params = {
            "api_key": api_key,
            "start_date": str(from_date),
            "end_date": str(to_date),
        }

        resp = requests.get(f"{AMS_METEORS_API_BASE}/get_events", params=params, timeout=HTTP_TIMEOUT)
        resp.raise_for_status()
        data = resp.json() or {}

        events = []
        if (data.get("status") == 200) and isinstance(data.get("result"), list):
            for event in data["result"]:
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
                        "visibility": event.get("visibility", "Unknown"),
                    },
                })
        return events
    except (HTTPError, RequestException, ValueError) as e:
        print(f"Error fetching meteor shower events: {e}")
        return []


def fetch_fireball_events(from_date=None, to_date=None, api_key=None, latitude=None, longitude=None):
    """
    Fetch fireball sighting events from AMS Meteors API and return standardized events.
    If no key is provided/configured, returns [] (optional data source).
    """
    api_key = api_key or AMS_METEORS_API_KEY
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
            "pending_only": 0,  # include confirmed reports
        }

        # If the endpoint supports proximity, include coordinates (harmless if ignored).
        if latitude and longitude:
            params["latitude"] = latitude
            params["longitude"] = longitude

        resp = requests.get(f"{AMS_METEORS_API_BASE}/get_close_reports", params=params, timeout=HTTP_TIMEOUT)
        resp.raise_for_status()
        data = resp.json() or {}

        events = []
        if (data.get("status") == 200) and isinstance(data.get("result"), list):
            for report in data["result"]:
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
                        "description": "Fireball sighting reported",
                        "location": f"{report.get('city', 'Unknown')}, {report.get('state', 'Unknown')}",
                        "brightness": report.get("brightness", "Unknown"),
                        "trajectory": report.get("trajectory", "Unknown"),
                    },
                })
        return events
    except (HTTPError, RequestException, ValueError) as e:
        print(f"Error fetching fireball events: {e}")
        return []


def standardize_event_data(event_data, source_api):
    """
    Transform API responses into unified format.
    Currently a pass-through because fetchers already standardize their output.
    """
    return event_data
