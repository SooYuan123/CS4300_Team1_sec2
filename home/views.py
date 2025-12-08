from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.forms import UserCreationForm
from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.conf import settings
from django import forms
from datetime import date, datetime, timezone, timedelta
import os
import requests
import json
from openai import OpenAI
from dotenv import load_dotenv
from .models import Favorite, UserProfile
from .forms import UserUpdateForm, ProfileUpdateForm
from .utils import (
    fetch_astronomical_events,
    fetch_twilight_events,
    fetch_meteor_shower_events,
    fetch_fireball_events,
    get_celestial_bodies_with_visibility,
    fetch_rise_set_times,
    fetch_moon_phase,
    fetch_solar_eclipse_data,
    fetch_weather_forecast,
)

load_dotenv()

# Optional API keys for index/gallery helpers
NASA_API_KEY = os.getenv("NASA_API_KEY")
JWST_API_KEY = os.getenv("JWST_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


# -------------------------
# Gallery (html-images feature)
# -------------------------
def gallery(request):
    nasa_url = "https://images-api.nasa.gov/search?q=space&media_type=image"
    images = []

    try:
        response = requests.get(nasa_url, timeout=5)
        response.raise_for_status()
        data = response.json()

        items = (data.get("collection") or {}).get("items") or []
        for item in items[:40]:  # limit number of images
            links = item.get("links") or []
            data_block = item.get("data") or []
            if not links or not data_block:
                continue

            link = links[0].get("href")
            title = data_block[0].get("title", "NASA Image")
            description = data_block[0].get("description", "")
            if link:
                images.append({"src": link, "title": title, "desc": description})
    except Exception as e:
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

    user_favorites = []
    if request.user.is_authenticated:
        user_favorites = Favorite.objects.filter(user=request.user).values_list('image_url', flat=True)

    return render(request, "gallery.html", {"images": images})


# -------------------------
# Events pages / API
# -------------------------
def events_list(request):
    """Render the events page with first 20 events and celestial body positions"""
    latitude, longitude = "38.8339", "-104.8214"  # Colorado Springs, CO

    # Defaults in case downstream calls fail
    celestial_bodies = []
    moon_phase = None
    solar_eclipses = []
    weather_forecast = []

    try:
        events_data = fetch_all_events(latitude, longitude)
        print(f"DEBUG: Fetched {len(events_data)} total events")

        initial_events = events_data[:20]
        has_more = len(events_data) > 20

        print(f"DEBUG: Initial events: {len(initial_events)}, has_more: {has_more}")

        # Fetch Celestial Body Positions
        try:
            celestial_bodies = get_celestial_bodies_with_visibility(
                latitude=float(latitude),
                longitude=float(longitude)
            )
            print(f"DEBUG: Fetched {len(celestial_bodies)} celestial bodies")
        except Exception as e:
            print(f"ERROR fetching celestial bodies: {e}")

        # Fetch current moon phase
        try:
            moon_phase = fetch_moon_phase(
                datetime.now(timezone.utc),
                float(latitude),
                float(longitude)
            )
        except Exception as e:
            print(f"ERROR fetching moon phase: {e}")

        # Fetch upcoming solar eclipses
        try:
            solar_eclipses = fetch_solar_eclipse_data()
            if isinstance(solar_eclipses, dict) and 'response' in solar_eclipses:
                solar_eclipses = list(solar_eclipses['response'].values())[:5]  # Get next 5
        except Exception as e:
            print(f"ERROR fetching solar eclipses: {e}")

        # Fetch Open-Meteo Weather
        try:
            raw_weather = fetch_weather_forecast(latitude, longitude)

            if raw_weather and 'time' in raw_weather:
                # Get current hour to filter past data
                # Note: This uses server time. For local dev, this is your computer time.
                current_hour = datetime.now().strftime("%Y-%m-%dT%H:00")

                times = raw_weather.get('time', [])
                covers = raw_weather.get('cloud_cover', [])
                visibilities = raw_weather.get('visibility', [])
                precips = raw_weather.get('precipitation_probability', [])

                for i, t in enumerate(times):
                    # Only add future hours (or current hour)
                    if t >= current_hour:
                        weather_forecast.append({
                            'time': t,
                            'cloud_cover': covers[i] if i < len(covers) else 0,
                            'visibility': visibilities[i] if i < len(visibilities) else 0,
                            'precipitation_probability': precips[i] if i < len(precips) else 0,
                        })

                        # Stop after we have 12 hours of future data
                        if len(weather_forecast) >= 12:
                            break

        except Exception as e:
            print(f"ERROR fetching weather: {e}")

        return render(request, "events_list.html", {
            "events": initial_events,
            "has_more": has_more,
            "celestial_bodies": celestial_bodies,
            "location": "Colorado Springs, CO",
            "moon_phase": moon_phase,
            "solar_eclipses": solar_eclipses,
            "weather_forecast": weather_forecast,
        })
    except Exception as e:
        print(f"ERROR in events_list: {e}")
        return render(request, "events_list.html", {
            "events": [],
            "has_more": False,
            "celestial_bodies": [],
            "location": "Colorado Springs, CO",
            "moon_phase": None,
            "solar_eclipses": [],
            "weather_forecast": [],
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
        latitude, longitude = "38.8339", "-104.8214"  # Colorado Springs, CO

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
    """
    Fetch events from all available sources and sort chronologically:
      - Astronomy API: celestial body events
      - Open-Meteo API: astronomical twilight events
      - AMS Meteors API: showers + fireballs (if API key available)
    """
    events_data = []

    print("Fetching celestial body events from Astronomy API...")
    celestial_bodies = ["sun", "moon", "mercury", "venus", "mars", "jupiter", "saturn", "uranus", "neptune", "pluto"]

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
                    # Use transit time as peak if available
                    transit = row.get("transit")
                    if transit and transit.get("date"):
                        peak_date = transit.get("date")
                    else:
                        continue

                # Dedupe on (peak, body) so Sun & Moon at same time both appear
                dedup_key = (peak_date, base_name)
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)

                events_data.append({
                    "body": base_name,
                    "type": (events[0].get("type") if events else "rise-set"),
                    "peak": peak_date,
                    "rise": row.get("rise", {}).get("date") if row.get("rise") else None,
                    "set": row.get("set", {}).get("date") if row.get("set") else None,
                    "transit": row.get("transit", {}).get("date") if row.get("transit") else None,
                    "obscuration": (row.get("extraInfo") or {}).get("obscuration"),
                    "highlights": (events[0].get("eventHighlights") if events else {}) or {},
                })
        except Exception as e:
            failures += 1
            print(f"Error fetching {body} events: {e}")

    # Open-Meteo twilight
    print("Fetching twilight events from Open-Meteo API...")
    try:
        twilight_events = fetch_twilight_events(latitude, longitude)
        events_data.extend(twilight_events)
        print(f"Added {len(twilight_events)} twilight events")
    except Exception as e:
        print(f"Error fetching twilight events: {e}")

    # AMS Meteors (optional)
    ams_api_key = getattr(settings, "AMS_METEORS_API_KEY", "")
    if ams_api_key:
        print("Fetching meteor shower events from AMS Meteors API...")
        try:
            meteor_events = fetch_meteor_shower_events(api_key=ams_api_key)
            events_data.extend(meteor_events)
            print(f"Added {len(meteor_events)} meteor shower events")
        except Exception as e:
            print(f"Error fetching meteor shower events: {e}")

        print("Fetching fireball events from AMS Meteors API...")
        try:
            fireball_events = fetch_fireball_events(
                api_key=ams_api_key, latitude=latitude, longitude=longitude
            )
            events_data.extend(fireball_events)
            print(f"Added {len(fireball_events)} fireball events")
        except Exception as e:
            print(f"Error fetching fireball events: {e}")
    else:
        print("AMS Meteors API key not configured, skipping meteor and fireball data")

    # If Astronomy API completely failed for every body, surface a hard error
    if successes == 0 and failures > 0:
        raise RuntimeError("Upstream Radiant Drift API failure")

    print(f"Total events fetched from all sources: {len(events_data)}")

    # Sort by parsed ISO peak time (UTC if available); tie-break by body name
    events_data.sort(
        key=lambda e: (
            _parse_iso(e["peak"]) or datetime.max.replace(tzinfo=timezone.utc),
            e["body"] or ""
        )
    )
    return events_data


def _parse_iso(dt_str: str):
    """
    Parse an ISO datetime string and always return an offset-aware UTC datetime.

    - Converts trailing 'Z' to '+00:00'
    - If no timezone info is present, assume UTC
    """
    if not dt_str:
        return None

    val = dt_str.replace("Z", "+00:00")  # handle trailing 'Z'
    try:
        dt = datetime.fromisoformat(val)
        if dt.tzinfo is None:
            # Assume UTC if no tzinfo provided
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None

# -------------------------
# Index (html-images feature: JWST/NASA)
# -------------------------
def get_jwst_random_image():
    """Fetch a deterministic 'random' JWST image (one per day)."""
    jwst_url = "https://api.jwstapi.com/all/type/jpg?page=1&perPage=30"

    if not JWST_API_KEY:
        print("JWST_API_KEY not set.")
        return None

    try:
        headers = {"X-API-KEY": JWST_API_KEY}
        resp = requests.get(jwst_url, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            body = data.get("body") if isinstance(data, dict) else None
            if body:
                non_thumb = [item for item in body if "_thumb" not in item.get("id", "")]
                images = non_thumb or body
                idx = date.today().toordinal() % len(images)
                return images[idx]
        else:
            print(f"JWST API returned status {resp.status_code}")
    except requests.RequestException as e:
        print("JWST API request failed:", e)
    return None


def get_jwst_recent_images(count=10):
    """Fetch recent JWST images."""
    jwst_url = f"https://api.jwstapi.com/all/type/jpg?page=1&perPage={count}"

    if not JWST_API_KEY:
        print("JWST_API_KEY not set.")
        return None

    try:
        headers = {"X-API-KEY": JWST_API_KEY}
        resp = requests.get(jwst_url, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                return data[:count]
            if isinstance(data, dict) and "body" in data:
                return (data["body"] or [])[:count]
        else:
            print(f"JWST API returned status {resp.status_code}")
    except requests.RequestException as e:
        print("JWST API request failed:", e)
    return None


def get_apod_for_date(d):
    """Fetch NASA APOD for a specific date."""
    apod_base_url = "https://api.nasa.gov/planetary/apod"
    if not NASA_API_KEY:
        print("NASA_API_KEY not set.")
        return None
    try:
        params = {"api_key": NASA_API_KEY, "date": d.isoformat()}
        resp = requests.get(apod_base_url, params=params, timeout=5)
        if resp.status_code == 200:
            return resp.json()
        else:
            print(f"NASA API returned status {resp.status_code} for date {d.isoformat()}")
    except requests.RequestException as e:
        print("NASA API request failed:", e)
    return None


def find_most_recent_apod(max_days_back=30):
    today = date.today()
    for i in range(max_days_back):
        d = today - timedelta(days=i)
        data = get_apod_for_date(d)
        if data:
            return data
    return None


def index(request):
    """Render index page with JWST image (fallback to APOD)."""
    jwst_image = None
    use_jwst = False  # set False to use NASA APOD fallback

    try:
        jwst_image = get_jwst_random_image() if use_jwst else find_most_recent_apod()
    except Exception as e:
        print("Error fetching space image:", e)

    context = {
        "space_image": jwst_image,
        "using_jwst": use_jwst,
    }
    return render(request, "index.html", context)


# -------------------------
# Auth
# -------------------------
class CustomUserCreationForm(UserCreationForm):
    """Custom registration form with required email"""
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Email address'
        })
    )

    class Meta:
        model = User
        fields = ('username', 'email', 'password1', 'password2')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Add Bootstrap classes to all fields
        for field_name in ['username', 'password1', 'password2']:
            self.fields[field_name].widget.attrs['class'] = 'form-control'

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        if commit:
            user.save()
        return user

def register(request):
    if request.method == "POST":
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(request, "Account created! You are now logged in.")
            auth_login(request, user)
            return redirect("index")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = UserCreationForm()
    return render(request, "auth/register.html", {"form": form})


def toggle_favorite(request):
    if not request.user.is_authenticated:
        return JsonResponse({'redirect': '/login/', 'message': 'Please login to add favorites.'}, status=401)

    image_url = request.POST.get('image_url')
    title = request.POST.get('title', '')
    desc = request.POST.get('desc', '')

    favorite, created = Favorite.objects.get_or_create(
        user=request.user,
        image_url=image_url,
        defaults={'title': title, 'desc': desc}
    )

    if not created:
        # If it already exists, unfavorite it
        favorite.delete()
        return JsonResponse({'favorited': False})
    else:
        return JsonResponse({'favorited': True})


def chatbot_api(request):
    """
    Handle chatbot API requests.
    Receives user messages and returns AI responses about astronomy.
    """
    if request.method != "POST":
        return JsonResponse({"error": "Only POST requests allowed"}, status=405)

    try:
        # Parse incoming JSON data
        data = json.loads(request.body)
        user_message = data.get("message", "").strip()

        if not user_message:
            return JsonResponse({"error": "Message cannot be empty"}, status=400)

        # Check if API key is configured
        if not OPENAI_API_KEY:
            return JsonResponse({
                "error": "OpenAI API key not configured. Please contact the administrator."
            }, status=500)

        # Initialize OpenAI client
        client = OpenAI(api_key=OPENAI_API_KEY)

        # Create a system message to set the AI's behavior
        system_message = """You are an expert astronomy assistant for CelestiaTrack, 
        a celestial event tracking application. You help users understand astronomy concepts, 
        celestial events, space phenomena, and answer questions about planets, stars, galaxies, 
        and the universe. Be informative, engaging, and educational. Keep responses concise 
        but thorough (2-4 paragraphs maximum unless asked for more detail). Use scientific 
        accuracy while remaining accessible to general audiences."""

        # Get conversation history from request (optional, for context)
        conversation_history = data.get("history", [])

        # Build messages array for API
        messages = [{"role": "system", "content": system_message}]

        # Add conversation history if provided (limit to last 10 messages for context)
        if conversation_history:
            messages.extend(conversation_history[-10:])

        # Add current user message
        messages.append({"role": "user", "content": user_message})

        # Call OpenAI API
        response = client.chat.completions.create(
            model="gpt-5-mini",
            messages=messages,
            max_completion_tokens=800,  # Limit response length
            temperature=1,  # Balance creativity and consistency
        )

        # Extract AI response
        ai_message = response.choices[0].message.content

        return JsonResponse({
            "response": ai_message,
            "success": True
        })

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON data"}, status=400)
    except Exception as e:
        print(f"Chatbot API Error: {e}")
        return JsonResponse({
            "error": f"An error occurred: {str(e)}"
        }, status=500)

@login_required
def favorites(request):
    favorites = Favorite.objects.filter(user=request.user)
    return render(request, "favorites.html", {"favorites": favorites})


@login_required
def profile_view(request, username=None):
    """
    Display user profile.
    If username is provided, show that user's profile.
    Otherwise, show the logged-in user's profile.
    """
    if username:
        # View another user's profile
        user = get_object_or_404(User, username=username)
    else:
        # View own profile
        user = request.user

    # Get or create profile
    profile, created = UserProfile.objects.get_or_create(user=user)

    context = {
        'profile_user': user,
        'profile': profile,
        'is_own_profile': request.user == user,
    }

    return render(request, 'profile.html', context)


@login_required
def profile_edit(request):
    """Edit user profile"""
    if request.method == 'POST':
        user_form = UserUpdateForm(request.POST, instance=request.user)
        profile_form = ProfileUpdateForm(
            request.POST,
            request.FILES,
            instance=request.user.profile
        )

        if user_form.is_valid() and profile_form.is_valid():
            user_form.save()
            profile_form.save()
            messages.success(request, 'Your profile has been updated successfully!')
            return redirect('profile', username=request.user.username)
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        user_form = UserUpdateForm(instance=request.user)
        profile_form = ProfileUpdateForm(instance=request.user.profile)

    context = {
        'user_form': user_form,
        'profile_form': profile_form,
    }

    return render(request, 'profile_edit.html', context)