import os
import base64
import requests
from datetime import datetime, timedelta, timezone
from requests.exceptions import HTTPError, RequestException
from django.conf import settings
from dotenv import load_dotenv

load_dotenv()

# -------------------------
# API base URLs
# -------------------------
ASTRONOMY_API_BASE = "https://api.astronomyapi.com/api/v2/bodies/events"
OPEN_METEO_API_BASE = "https://api.open-meteo.com/v1/forecast"
AMS_METEORS_API_BASE = "https://www.amsmeteors.org/members/api/open_api"

# Radiant Drift API
RADIANT_DRIFT_API_BASE = "https://api.radiantdrift.com"

# Solar System OpenData API
SOLAR_SYSTEM_API_BASE = "https://api.le-systeme-solaire.net/rest/bodies"


# -------------------------
# Auth helpers
# -------------------------
def get_auth_header():
    """Basic auth header for AstronomyAPI (used for general body events)."""
    app_id = getattr(settings, "ASTRONOMY_API_APP_ID", None) or os.getenv("ASTRONOMY_API_APP_ID")
    app_secret = getattr(settings, "ASTRONOMY_API_APP_SECRET", None) or os.getenv("ASTRONOMY_API_APP_SECRET")
    if not app_id or not app_secret:
        # Allow tests/CI/local without these creds
        return {}
    token = base64.b64encode(f"{app_id}:{app_secret}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def get_radiant_drift_auth_header():
    """Get authorization header for Radiant Drift API."""
    api_key = getattr(settings, "RADIANT_DRIFT_API_KEY", None) or os.getenv("RADIANT_DRIFT_API_KEY")
    if not api_key:
        raise ValueError("RADIANT_DRIFT_API_KEY not configured")
    return {"Authorization": f"RadiantDriftAuth {api_key}"}


def get_solar_system_auth_header():
    """Get authorization header for Solar System OpenData API (if ever needed)."""
    api_key = getattr(settings, "SOLAR_SYSTEM_API_KEY", None) or os.getenv("SOLAR_SYSTEM_API_KEY")
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}


# -------------------------
# Astronomy API (general celestial events)
# -------------------------
def fetch_astronomical_events(body, latitude, longitude, elevation=0, from_date=None, to_date=None):
    """Return Astronomy API rows[] or [] (404 -> [], 403 -> raise)."""
    today = datetime.now(timezone.utc).date()
    to_date = to_date or (today + timedelta(days=1095))   # ~3 years ahead
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
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json() or {}
        return ((data.get("data") or {}).get("rows")) or []
    except HTTPError as e:
        status = getattr(e.response, "status_code", None)
        if status == 404:
            return []
        if status == 403:
            # Credentials invalid / not allowed – bubble up
            raise
        print(f"HTTP error fetching {body}: {e}")
        return []
    except (RequestException, ValueError) as e:
        print(f"Error fetching AstronomyAPI {body}: {e}")
        return []


# -------------------------
# Radiant Drift – rise/set, positions, moon phase, eclipses
# -------------------------
def fetch_rise_set_times(body, latitude, longitude, from_date=None, to_date=None):
    """
    Fetch rise, transit, and set times from Radiant Drift API.
    Only supports 'sun' and 'moon'.

    Returns a list of rows shaped similarly to AstronomyAPI rows so the
    rest of the code can treat them uniformly.
    """
    if body.lower() not in ["sun", "moon"]:
        return []  # Radiant Drift only supports sun and moon

    today = datetime.now(timezone.utc).date()

    # Default window: today to next 90 days
    if not to_date:
        to_date = today + timedelta(days=90)
    if not from_date:
        from_date = today

    # Convert to ISO strings
    if isinstance(from_date, (datetime, type(today))):
        from_date_str = from_date.isoformat() if hasattr(from_date, "isoformat") else str(from_date)
    else:
        from_date_str = str(from_date)

    if isinstance(to_date, (datetime, type(today))):
        to_date_str = to_date.isoformat() if hasattr(to_date, "isoformat") else str(to_date)
    else:
        to_date_str = str(to_date)

    # Add time component if not present
    if "T" not in from_date_str:
        from_date_str += "T00:00:00Z"
    if "T" not in to_date_str:
        to_date_str += "T23:59:59Z"

    url = f"{RADIANT_DRIFT_API_BASE}/rise-set/{from_date_str}/{to_date_str}"

    params = {
        "lat": latitude,
        "lng": longitude,
        "body": body.lower(),
    }

    try:
        response = requests.get(
            url,
            headers=get_radiant_drift_auth_header(),
            params=params,
            timeout=10,
        )
        if response.status_code == 404:
            return []
        response.raise_for_status()
        data = response.json()

        events = []
        if "response" in data:
            for date_key, date_data in data["response"].items():
                if body in date_data:
                    body_data = date_data[body]
                    event = {
                        "date": date_key,
                        "body": {"name": body.capitalize()},
                        "rise": {"date": body_data.get("rise", {}).get("utc")} if "rise" in body_data else None,
                        "transit": {"date": body_data.get("transit", {}).get("utc")} if "transit" in body_data else None,
                        "set": {"date": body_data.get("set", {}).get("utc")} if "set" in body_data else None,
                        "events": [
                            {
                                "type": "rise-set",
                                "eventHighlights": {
                                    "peak": {"date": body_data.get("transit", {}).get("utc")}
                                },
                            }
                        ],
                    }
                    events.append(event)

        return events
    except HTTPError as e:
        if getattr(e, "response", None) is not None and e.response.status_code == 404:
            return []
        print(f"Error fetching rise/set times for {body}: {e}")
        raise
    except Exception as e:
        print(f"Error fetching rise/set times for {body}: {e}")
        return []


def fetch_body_position(body, date_time, latitude, longitude):
    """
    Fetch body position from Radiant Drift API.
    Only supports 'sun', 'moon', and 'galactic-center'.
    """
    if body.lower() not in ["sun", "moon", "galactic-center"]:
        return None

    # Ensure date_time is ISO format
    if isinstance(date_time, datetime):
        date_time_str = date_time.isoformat()
    else:
        date_time_str = str(date_time)

    if "Z" not in date_time_str and "+" not in date_time_str:
        date_time_str += "Z"

    url = f"{RADIANT_DRIFT_API_BASE}/body-position/{date_time_str}"

    params = {
        "lat": latitude,
        "lng": longitude,
        "body": body.lower(),
    }

    try:
        response = requests.get(
            url,
            headers=get_radiant_drift_auth_header(),
            params=params,
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()

        if "response" in data and date_time_str in data["response"]:
            return data["response"][date_time_str].get(body.lower())

        return None
    except Exception as e:
        print(f"Error fetching position for {body}: {e}")
        return None


def fetch_moon_phase(date_time, latitude, longitude):
    """
    Fetch moon phase information from Radiant Drift API.
    """
    position_data = fetch_body_position("moon", date_time, latitude, longitude)

    if position_data:
        return {
            "illumination": position_data.get("illuminatedFraction"),
            "phase": position_data.get("phase"),
            "age": position_data.get("age"),
        }

    return None


def fetch_solar_eclipse_data(from_date=None, to_date=None):
    """
    Fetch solar eclipse data from Radiant Drift API.
    """
    today = datetime.now(timezone.utc).date()

    if not to_date:
        to_date = today + timedelta(days=1095)  # ~3 years
    if not from_date:
        from_date = today

    # Convert to ISO strings
    if isinstance(from_date, (datetime, type(today))):
        from_date_str = from_date.isoformat() if hasattr(from_date, "isoformat") else str(from_date)
    else:
        from_date_str = str(from_date)

    if isinstance(to_date, (datetime, type(today))):
        to_date_str = to_date.isoformat() if hasattr(to_date, "isoformat") else str(to_date)
    else:
        to_date_str = str(to_date)

    if "T" not in from_date_str:
        from_date_str += "T00:00:00Z"
    if "T" not in to_date_str:
        to_date_str += "T23:59:59Z"

    url = f"{RADIANT_DRIFT_API_BASE}/solar-eclipse/{from_date_str}/{to_date_str}"

    try:
        response = requests.get(
            url,
            headers=get_radiant_drift_auth_header(),
            timeout=10,
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error fetching solar eclipse data: {e}")
        return []


# -------------------------
# Open-Meteo – twilight events
# -------------------------
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
                    "highlights": {
                        "source": "open_meteo",
                        "category": "twilight",
                        "description": "Beginning of astronomical twilight",
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
                        "description": "End of astronomical twilight",
                    },
                })
        return events
    except Exception as e:
        print(f"Error fetching twilight events: {e}")
        return []


# -------------------------
# AMS Meteors – showers + fireballs (optional)
# -------------------------
def fetch_meteor_shower_events(from_date=None, to_date=None, api_key=None):
    """AMS meteors (optional): returns list; [] if no key or error."""
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


# -------------------------
# Solar System OpenData + visibility helpers
# -------------------------
def fetch_celestial_body_positions():
    """Fetch celestial body data from Solar System OpenData API."""
    celestial_bodies = ["sun", "moon", "mercury", "venus", "mars", "jupiter", "saturn", "uranus", "neptune"]

    positions = []

    for body in celestial_bodies:
        try:
            response = requests.get(f"{SOLAR_SYSTEM_API_BASE}/{body}", timeout=5)
            if response.status_code == 200:
                data = response.json()

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
    Uses Radiant Drift for sun/moon, simplified logic for planets.

    Default Location: Colorado Springs, CO (38.8339°N, -104.8214°W)
    """
    body_lower = body_name.lower()

    try:
        # For sun and moon, use Radiant Drift API
        if body_lower in ["sun", "moon"]:
            rows = fetch_rise_set_times(body_lower, latitude, longitude)
            if not rows:
                return None

            now = datetime.now(timezone.utc)

            for row in rows:
                rise_time = row.get("rise", {})
                if rise_time and rise_time.get("date"):
                    rise_date_str = rise_time.get("date")
                    try:
                        rise_date = datetime.fromisoformat(rise_date_str.replace("Z", "+00:00"))
                        if rise_date > now:
                            return rise_date
                    except Exception:
                        continue
            return None
        else:
            # For planets, we can't get precise visibility from available APIs
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

    # Sort By Next Visibility (None values go to the end)
    positions.sort(key=lambda x: x["nextVisible"] or datetime.max.replace(tzinfo=None))

    return positions
