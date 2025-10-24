from django.shortcuts import render
from django.http import JsonResponse
from .utils import fetch_astronomical_events
from datetime import datetime, timezone


def index(request):
    return render(request, 'index.html')


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