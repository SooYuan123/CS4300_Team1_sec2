from django.shortcuts import render
from django.http import JsonResponse
from .utils import fetch_all_events
from datetime import datetime
from requests.exceptions import HTTPError, ConnectionError, Timeout

def index(request):
    return render(request, 'index.html')

def events_list(request):
    """Render the events page with first 20 events"""
    latitude, longitude = "38.775867", "-84.39733"
    
    try:
        events_data = fetch_all_events(latitude, longitude)
        # print(f"DEBUG: Fetched {len(events_data)} total events")
        
        # Get first 20 events for initial render
        initial_events = events_data[:20]
        has_more = len(events_data) > 20
        
        # print(f"DEBUG: Initial events: {len(initial_events)}, has_more: {has_more}")
        
        return render(request, "events_list.html", {
            "events": initial_events,
            "has_more": has_more
        })
    except (HTTPError, ConnectionError, Timeout, RuntimeError) as e:
        print(f"ERROR in events_list: {e}")
        return render(request, "events_list.html", {
            "events": [],
            "has_more": False,
            "error_message": "Failed to fetch events due to an API error. Please check credentials."
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
        
        # print(f"DEBUG API: offset={offset}, limit={limit}, total={len(all_events)}, slice={len(events_slice)}, has_more={has_more}")
        
        return JsonResponse({
            "events": events_slice,
            "has_more": has_more
        }, status=200)
    except (HTTPError, ConnectionError, Timeout, RuntimeError) as e:
        print(f"ERROR in events_api: {e}")
        return JsonResponse({
            "events": [],
            "has_more": False,
            "error": str(e)
        }, status=500) # Returns status 500 on API/Auth crash