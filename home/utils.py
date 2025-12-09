import os
import base64
from datetime import datetime, timedelta, timezone

import requests
import ephem
from requests.exceptions import HTTPError, RequestException
from dotenv import load_dotenv
from django.conf import settings


load_dotenv()

# -------------------------
# API base URLs
# -------------------------
ASTRONOMY_API_BASE = "https://api.astronomyapi.com/api/v2/bodies/events"
OPEN_METEO_API_BASE = "https://api.open-meteo.com/v1/forecast"
AMS_METEORS_API_BASE = "https://api.amsmeteors.org/api/v1"


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
    """
    Solar System OpenData (le-systeme-solaire.net) auth:
      Authorization: Bearer <token>
    """
    api_key = getattr(settings, "SSOD_APP_ID", None) or os.getenv("SSOD_APP_ID")
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
                        "rise": {"date": body_data.get("rise", {}).get("utc")}
                        if "rise" in body_data else None,
                        "transit": {"date": body_data.get("transit", {}).get("utc")}
                        if "transit" in body_data else None,
                        "set": {"date": body_data.get("set", {}).get("utc")}
                        if "set" in body_data else None,
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


def fetch_twilight_events(latitude, longitude, _from_date=None, _to_date=None):
    """
    Open-Meteo: returns list of sunrise/sunset events; logs and returns [] on error.

    We keep this deliberately simple to avoid 400s:
      - No start_date / end_date
      - Use default forecast window (7 days) and no past days
    """
    try:
        params = {
            "latitude": float(latitude),
            "longitude": float(longitude),
            "daily": "sunrise,sunset",
            "timezone": "auto",
            "past_days": 0,   # no past days, just upcoming
        }

        r = requests.get(OPEN_METEO_API_BASE, params=params, timeout=15)
        r.raise_for_status()
        data = r.json() or {}
        daily = data.get("daily", {})
        dates = daily.get("time", []) or []
        sunrises = daily.get("sunrise", []) or []
        sunsets = daily.get("sunset", []) or []

        events = []
        for i, _date_str in enumerate(dates):
            # Sunrise
            if i < len(sunrises) and sunrises[i]:
                events.append({
                    "body": "Sun",
                    "type": "Sunrise",
                    "peak": sunrises[i],  # ISO timestamp from API
                    "rise": sunrises[i],
                    "set": None,
                    "obscuration": None,
                    "highlights": {
                        "source": "open_meteo",
                        "category": "twilight",
                        "description": "Local sunrise time",
                    },
                })
            # Sunset
            if i < len(sunsets) and sunsets[i]:
                events.append({
                    "body": "Sun",
                    "type": "Sunset",
                    "peak": sunsets[i],
                    "rise": sunsets[i],
                    "set": None,
                    "obscuration": None,
                    "highlights": {
                        "source": "open_meteo",
                        "category": "twilight",
                        "description": "Local sunset time",
                    },
                })

        return events
    except HTTPError as e:
        status = getattr(e.response, "status_code", None)
        # Try to log something useful without spamming the full response
        print(f"Open-Meteo HTTP {status} for twilight events; returning [].")
        return []
    except Exception as e:
        print(f"Error fetching twilight events: {e}")
        return []


def fetch_weather_forecast(latitude, longitude):
    """
    Fetch cloud cover and visibility data from Open-Meteo.
    """
    try:
        params = {
            "latitude": float(latitude),
            "longitude": float(longitude),
            "hourly": "cloud_cover,visibility,precipitation_probability",
            "timezone": "auto",
        }

        # Re-use the existing OPEN_METEO_API_BASE
        r = requests.get(OPEN_METEO_API_BASE, params=params, timeout=10)
        r.raise_for_status()
        # Return the whole dictionary
        return r.json()
    except Exception as e:
        print(f"Error fetching weather forecast: {e}")
        return {}

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


def fetch_fireball_events(
    from_date=None,
    to_date=None,
    api_key=None,
    latitude=None,
    longitude=None,
):  # pylint: disable=unused-argument
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
            response = requests.get(
                f"{SOLAR_SYSTEM_API_BASE}/{body}",
                headers=get_solar_system_auth_header(),
                timeout=5
            )
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
    Calculate the next rising time for a celestial body using PyEphem.
    This works locally and does not require an API key.
    """
    try:
        # 1. Setup Observer (The Viewer)
        observer = ephem.Observer()
        observer.lat = str(latitude)
        observer.lon = str(longitude)
        observer.elevation = 1800  # Approx elevation for Colorado Springs (meters)

        # Set current time (UTC)
        observer.date = datetime.now(timezone.utc)

        # 2. Map body name to Ephem object
        body_map = {
            'sun': ephem.Sun(),
            'moon': ephem.Moon(),
            'mercury': ephem.Mercury(),
            'venus': ephem.Venus(),
            'mars': ephem.Mars(),
            'jupiter': ephem.Jupiter(),
            'saturn': ephem.Saturn(),
            'uranus': ephem.Uranus(),
            'neptune': ephem.Neptune(),
            'pluto': ephem.Pluto()
        }

        target_body = body_map.get(body_name.lower())

        if not target_body:
            return None

        # 3. Calculate next rising time
        # next_rising returns an ephem Date object
        try:
            rise_time_ephem = observer.next_rising(target_body)

            # Convert ephem date to Python datetime
            rise_dt = rise_time_ephem.datetime()

            # Add UTC timezone info (ephem uses UTC by default)
            rise_dt = rise_dt.replace(tzinfo=timezone.utc)

            return rise_dt
        except ephem.AlwaysUpError:
            # Body is circumpolar (always visible, like stars near the pole)
            return datetime.now(timezone.utc)
        except ephem.NeverUpError:
            # Body is never visible (below horizon for this latitude)
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


def fetch_aurora_data():
    """
    Fetches the Planetary K-index from NOAA SWPC.
    Returns the latest K-index (0-9) and a status string.
    """
    try:
        # NOAA's 1-minute K-index JSON
        url = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json"
        response = requests.get(url, timeout=5)
        response.raise_for_status()

        data = response.json()
        # Data format is a list of lists. First is header. Last is most recent.
        # [time, kp, a_running, station_count]
        if len(data) > 1:
            latest = data[-1]
            kp_index = float(latest[1])

            # Determine status
            if kp_index >= 5:
                status = "High (Storm)"
                color = "danger"
            elif kp_index >= 4:
                status = "Moderate"
                color = "warning"
            else:
                status = "Low"
                color = "success"

            return {
                "kp_index": kp_index,
                "status": status,
                "color": color,
                "timestamp": latest[0]
            }
    except Exception as e:
        print(f"Error fetching Aurora data: {e}")

    return None
