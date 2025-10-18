# events/utils.py
import os
import base64
import hmac
import hashlib
import datetime
import requests
from dotenv import load_dotenv
from datetime import datetime, timedelta

load_dotenv()

ASTRONOMY_API_BASE = "https://api.astronomyapi.com/api/v2/bodies/events"
ASTRONOMY_API_APP_ID = "YOUR_APP_ID"
ASTRONOMY_API_APP_SECRET = "YOUR_APP_SECRET"

# Example observer location
OBSERVER = {
    "latitude": 39.419374,
    "longitude": -104.328805,
    "elevation": 0     # In feet? 
}

def get_auth_header():
    userpass = f"{ASTRONOMY_API_APP_ID}:{ASTRONOMY_API_APP_SECRET}"
    auth_string = base64.b64encode(userpass.encode()).decode()
    return {"Authorization": f"Basic {auth_string}"}

def fetch_eclipse_events():
    """Fetch solar/lunar eclipses within a date range"""
    headers = get_auth_header()
    today = datetime.utcnow().date()
    from_date = today.isoformat()
    to_date = (today + timedelta(days=365)).isoformat()  # full year window
    time = "12:00:00"

    events = []
    for body in ["sun", "moon"]:
        url = f"{ASTRONOMY_API_BASE}/bodies/events/{body}"
        params = {
            "latitude": OBSERVER["latitude"],
            "longitude": OBSERVER["longitude"],
            "elevation": OBSERVER["elevation"],
            "from_date": from_date,
            "to_date": to_date,
            "time": time,
            "output": "rows"
        }

        response = requests.get(url, headers=headers, params=params)
        if response.status_code == 200:
            rows = response.json().get("data", {}).get("rows", [])
            for row in rows:
                for event in row.get("events", []):
                    e_high = event.get("eventHighlights", {})
                    peak = e_high.get("peak", {})
                    events.append({
                        "category": "Eclipse",
                        "name": row["body"]["name"],
                        "type": event.get("type", "Unknown").replace("_", " ").title(),
                        "utc_time": peak.get("date", "N/A"),
                        "visibility": f"Altitude: {peak.get('altitude', 'N/A')}",
                        "description": " ".join(
                            f"{k}: {v['date']}" for k, v in e_high.items() if v
                        ) or "No details"
                    })
        else:
            print(f"Error fetching eclipses for {body}: {response.status_code}")

    return events


def fetch_meteor_showers():
    """Fetch meteor shower events if available"""
    headers = get_auth_header()
    url = f"{ASTRONOMY_API_BASE}/events"
    params = {
        "latitude": OBSERVER["latitude"],
        "longitude": OBSERVER["longitude"],
        "elevation": OBSERVER["elevation"],
        "from_date": datetime.utcnow().date().isoformat(),
        "to_date": (datetime.utcnow().date() + timedelta(days=365)).isoformat(),
        "time": "12:00:00"
    }

    response = requests.get(url, headers=headers, params=params)
    events = []

    if response.status_code == 200:
        rows = response.json().get("data", {}).get("rows", [])
        for row in rows:
            for event in row.get("events", []):
                events.append({
                    "category": "Meteor Shower",
                    "name": row["body"]["name"],
                    "type": event.get("type", "N/A").replace("_", " ").title(),
                    "utc_time": event.get("peak", {}).get("date", "N/A"),
                    "visibility": f"Altitude: {event.get('peak', {}).get('altitude', 'N/A')}",
                    "description": "Meteor shower or related celestial event."
                })
    else:
        print(f"Meteor shower request failed: {response.status_code} - {response.text}")

    return events


def fetch_visible_objects():
    """Fetch bright or notable objects (e.g., planets, DSOs)"""
    headers = get_auth_header()
    url = f"{ASTRONOMY_API_BASE}/bodies/search"
    params = {"limit": 5, "offset": 0}
    response = requests.get(url, headers=headers, params=params)
    objects = []

    if response.status_code == 200:
        data = response.json().get("data", [])
        for obj in data:
            objects.append({
                "category": "Visible Object",
                "name": obj.get("name"),
                "type": obj.get("type", {}).get("name", "Unknown"),
                "utc_time": "Ongoing",
                "visibility": obj.get("position", {}).get("constellation", {}).get("name", "Unknown"),
                "description": obj.get("subType", {}).get("name", "No subtype info")
            })
    else:
        print(f"Error fetching visible objects: {response.status_code}")

    return objects


def fetch_astronomical_events():
    """Combine all events from multiple sources"""
    all_events = []
    all_events.extend(fetch_eclipse_events())
    all_events.extend(fetch_meteor_showers())
    all_events.extend(fetch_visible_objects())
    return all_events