from django.shortcuts import render, redirect
from django.contrib.auth.forms import UserCreationForm
from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.http import JsonResponse
from .utils import fetch_astronomical_events
from datetime import date, datetime, timezone, timedelta
import requests
from dotenv import load_dotenv
import os
from django.contrib.auth.decorators import login_required

load_dotenv()


NASA_API_KEY = os.getenv("NASA_API_KEY")

@login_required
def gallery(request):
    nasa_url = "https://images-api.nasa.gov/search?q=space&media_type=image"
    images = []

    try:
        response = requests.get(nasa_url, timeout=5)
        response.raise_for_status()
        data = response.json()
        print(data.keys())

        # Safely get to the list of items in NASA's response
        items = data.get("collection", {}).get("items", [])
        
        for item in items[:40]:  # limit to # of images
            links = item.get("links", [])
            data_block = item.get("data", [])
            if not links or not data_block:
                continue

            link = links[0].get("href")
            title = data_block[0].get("title", "NASA Image")
            description = data_block[0].get("description", "")
            if link:
                images.append({
                    "src": link,
                    "title": title,
                    "desc": description,
                })

    except Exception as e:
        # print the error (for development)
        print("NASA API fetch failed:", e)

        # Fallback static images
        images = [
            {"src": "https://images.unsplash.com/photo-1451187580459-43490279c0fa?auto=format&fit=crop&w=1200&q=80"},
            {"src": "https://images.unsplash.com/photo-1529788295308-1eace6f67388?auto=format&fit=crop&w=1200&q=80"},
            {"src": "https://images.unsplash.com/photo-1462331940025-496dfbfc7564?auto=format&fit=crop&w=1200&q=80"},
            {"src": "https://images.unsplash.com/photo-1706562018171-7fefa57d37af?auto=format&fit=crop&w=1200&q=80"},
            {"src": "https://images.unsplash.com/photo-1706211306896-92c4abb298d7?auto=format&fit=crop&w=1200&q=80"},
            {"src": "https://images.unsplash.com/photo-1707058665549-c2a27e3fad45?auto=format&fit=crop&w=1200&q=80"},
        ]

    return render(request, "gallery.html", {"images": images})

def events_list(request):
    """Render the events page with first 20 events"""
    latitude, longitude = "38.775867", "-84.39733"

    try:
        events_data = fetch_all_events(latitude, longitude)
        print(f"DEBUG: Fetched {len(events_data)} total events")

        # Get first 20 events for initial render
        initial_events = events_data[:20]
        has_more = len(events_data) > 20

        print(f"DEBUG: Initial events: {len(initial_events)}, has_more: {has_more}")

        return render(request, "events_list.html", {
            "events": initial_events,
            "has_more": has_more
        })
    except Exception as e:
        print(f"ERROR in events_list: {e}")
        return render(request, "events_list.html", {
            "events": [],
            "has_more": False
        })

def _earliest_peak_from_events(events):
    """Return the earliest peak date string across an events list."""
    if not events:
        return None
    peaks = []
    for ev in events:
        peak = ((ev.get("eventHighlights") or {}).get("peak") or {}).get("date")
        if peak:
            peaks.append(_parse_iso(peak))
    if not peaks:
        return None
    earliest = min(peaks)
    # return the original string form expected by the API/json
    # convert back to isoformat, keeping 'Z' if UTC
    if earliest and earliest.tzinfo:
        if earliest.utcoffset() == timezone.utc.utcoffset(earliest):
            return earliest.replace(tzinfo=None).isoformat() + "Z"
    return earliest.isoformat()

def events_api(request):
    """Return events with offset/limit and proper has_more; return 500 on catastrophic failure."""
    try:
        offset = int(request.GET.get("offset", 0))
        limit = int(request.GET.get("limit", 20))
        latitude, longitude = "38.775867", "-84.39733"

        all_events = fetch_all_events(latitude, longitude)
        total = len(all_events)
        slice_ = all_events[offset:offset + limit]
        has_more = (offset + len(slice_)) < total

        return JsonResponse({
            "events": slice_,
            "total": total,
            "offset": offset,
            "limit": limit,
            "has_more": has_more,
            "error": False,
        }, status=200)
    except Exception as e:
        # Tests expect HTTP 500 on catastrophic failure
        return JsonResponse({
            "events": [],
            "total": 0,
            "offset": 0,
            "limit": 0,
            "has_more": False,
            "error": True,
            "message": str(e),
        }, status=500)

def fetch_all_events(latitude, longitude):
    """Fetch events, dedupe by (peak, body), and sort chronologically with a stable body tie-break."""
    celestial_bodies = ["sun","moon","mercury","venus","mars",
                        "jupiter","saturn","uranus","neptune","pluto"]

    events_data = []
    seen = set()  # (peak_date_str, body_name)
    failures = 0
    successes = 0

    for body in celestial_bodies:
        try:
            rows = fetch_astronomical_events(body, latitude, longitude)
            if not rows:
                continue
            successes += 1

            for row in rows:
                name = (row.get("body", {}) or {}).get("name", "")
                base_name = name.split()[0] if name else body.capitalize()

                events = row.get("events") or []
                peak_date = _earliest_peak_from_events(events)
                if not peak_date:
                    continue

                # NEW: dedupe on (peak, body) so Sun & Moon at same time both appear
                dedup_key = (peak_date, base_name)
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)

                events_data.append({
                    "body": base_name,
                    "type": (events[0].get("type") if events else None),
                    "peak": peak_date,
                    "rise": row.get("rise"),
                    "set": row.get("set"),
                    "obscuration": (row.get("extraInfo") or {}).get("obscuration"),
                    "highlights": (events[0].get("eventHighlights") if events else {}) or {},
                })
        except Exception as e:
            failures += 1
            print(f"Error fetching {body} events: {e}")

    if successes == 0 and failures > 0:
        raise RuntimeError("Upstream Astronomy API failure")

    # NEW: tie-break by body name so Moon sorts before Sun when times are equal
    events_data.sort(
        key=lambda e: (
            _parse_iso(e["peak"]) or datetime.max.replace(tzinfo=timezone.utc),
            e["body"] or ""
        )
    )
    return events_data

def _parse_iso(dt_str: str):
    if not dt_str:
        return None
    # handle trailing 'Z' → ISO aware datetime
    val = dt_str.replace('Z', '+00:00')
    try:
        return datetime.fromisoformat(val)
    except Exception:
        return None

def get_apod_for_date(d):
    apod_base_url = "https://api.nasa.gov/planetary/apod"
    """Fetch APOD for a specific date."""
    if not NASA_API_KEY:
        print("NASA_API_KEY not set.")
        return None
    try:
        params = {"api_key": NASA_API_KEY, "date": d.isoformat()}
        resp = requests.get(apod_base_url, params=params, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            return data
        else:
            print(f"NASA API returned status {resp.status_code} for date {d.isoformat()}")
    except requests.RequestException as e:
        print("NASA API request failed:", e)
    return None

def find_most_recent_apod(max_days_back=30):
    # today = date.today()

    # Use actual date
    from datetime import date as date_class
    today = date_class(2025, 10, 1)  # Actual date
    for i in range(max_days_back):
        d = today - timedelta(days=i)
        data = get_apod_for_date(d)
        if data:
            return data
    return None

def index(request):
    """Render index page with APOD."""
    apod = None
    try:
        apod = find_most_recent_apod()
    except Exception as e:
        print("Error fetching APOD:", e)

    context = {
        "apod": apod  # Could be None if fetch failed
    }
    return render(request, "index.html", context)

def register(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(request, 'Account created! You are now logged in.')
            auth_login(request, user)
            return redirect('index')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = UserCreationForm()
    return render(request, 'auth/register.html', {'form': form})