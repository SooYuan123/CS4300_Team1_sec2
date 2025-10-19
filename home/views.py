from django.shortcuts import render
from .utils import fetch_astronomical_events
from datetime import datetime

def index(request):
    return render(request, 'index.html')

def events_list(request):
    latitude, longitude = "38.775867", "-84.39733"
    events_data = []

    for body in ["sun", "moon"]:
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
    # Sort by peak date
    events_data = sorted(events_data, key=lambda e: e["peak"] or datetime.max)
    return render(request, "events_list.html", {"events": events_data})