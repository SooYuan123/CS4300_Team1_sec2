from django.shortcuts import render
from django.http import JsonResponse
from .utils import (
    fetch_astronomical_events, 
    fetch_twilight_events, 
    fetch_meteor_shower_events, 
    fetch_fireball_events
)
from datetime import datetime
from django.conf import settings

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

def events_api(request):
    """API endpoint for lazy loading events"""
    latitude, longitude = "38.775867", "-84.39733"
    
    try:
        # Get pagination parameters
        offset = int(request.GET.get('offset', 0))
        limit = int(request.GET.get('limit', 20))
        
        # Fetch all events
        all_events = fetch_all_events(latitude, longitude)
        
        # Get paginated slice
        start_idx = offset
        end_idx = offset + limit
        events_slice = all_events[start_idx:end_idx]
        has_more = end_idx < len(all_events)
        
        print(f"DEBUG API: offset={offset}, limit={limit}, total={len(all_events)}, slice={len(events_slice)}, has_more={has_more}")
        
        return JsonResponse({
            "events": events_slice,
            "has_more": has_more
        })
    except Exception as e:
        print(f"ERROR in events_api: {e}")
        return JsonResponse({
            "events": [],
            "has_more": False,
            "error": str(e)
        })

def fetch_all_events(latitude, longitude):
    """
    Fetch events from all available sources and sort chronologically
    
    Sources:
    - Astronomy API: Celestial body events (sun, moon, planets)
    - Open-Meteo API: Astronomical twilight events
    - AMS Meteors API: Meteor showers and fireball sightings (if API key available)
    """
    events_data = []
    
    # 1. Fetch celestial body events from Astronomy API
    print("Fetching celestial body events from Astronomy API...")
    celestial_bodies = ["sun", "moon", "mercury", "venus", "mars", "jupiter", "saturn", "uranus", "neptune", "pluto"]
    
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
    
    # 2. Fetch twilight events from Open-Meteo API
    print("Fetching twilight events from Open-Meteo API...")
    try:
        twilight_events = fetch_twilight_events(latitude, longitude)
        events_data.extend(twilight_events)
        print(f"Added {len(twilight_events)} twilight events")
    except Exception as e:
        print(f"Error fetching twilight events: {e}")
    
    # 3. Fetch meteor shower events from AMS Meteors API (if API key available)
    ams_api_key = getattr(settings, 'AMS_METEORS_API_KEY', '')
    if ams_api_key:
        print("Fetching meteor shower events from AMS Meteors API...")
        try:
            meteor_events = fetch_meteor_shower_events(api_key=ams_api_key)
            events_data.extend(meteor_events)
            print(f"Added {len(meteor_events)} meteor shower events")
        except Exception as e:
            print(f"Error fetching meteor shower events: {e}")
        
        # 4. Fetch fireball events from AMS Meteors API
        print("Fetching fireball events from AMS Meteors API...")
        try:
            fireball_events = fetch_fireball_events(
                api_key=ams_api_key, 
                latitude=latitude, 
                longitude=longitude
            )
            events_data.extend(fireball_events)
            print(f"Added {len(fireball_events)} fireball events")
        except Exception as e:
            print(f"Error fetching fireball events: {e}")
    else:
        print("AMS Meteors API key not configured, skipping meteor and fireball data")

    print(f"Total events fetched from all sources: {len(events_data)}")
    
    # Sort by peak date, using datetime.max for events without peak dates
    events_data = sorted(events_data, key=lambda e: e["peak"] or datetime.max.isoformat())
    return events_data