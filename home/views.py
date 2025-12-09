import os
import json
import base64
from datetime import date, datetime, timezone, timedelta
from io import BytesIO

import requests
from openai import OpenAI
from dotenv import load_dotenv
from PIL import Image

from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.forms import UserCreationForm
from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.conf import settings
from django import forms
from django.views.decorators.http import require_http_methods, require_GET

from .models import Favorite, EventFavorite, UserProfile
from .forms import UserUpdateForm, ProfileUpdateForm
from .utils import (
    fetch_astronomical_events,
    fetch_twilight_events,
    get_celestial_bodies_with_visibility,
    fetch_weather_forecast,
    fetch_aurora_data,
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
        user_favorites = Favorite.objects.filter(
            user=request.user
        ).values_list("image_url", flat=True)
    return render(
        request,
        "gallery.html",
        {
            "images": images,
            "user_favorites": list(user_favorites),
        },
    )


# -------------------------
# Events pages / API
# -------------------------

# pylint: disable=too-many-nested-blocks
def events_list(request):
    """Lightweight events page (no expensive API calls)."""
    return render(request, "events_list.html", {
        "location": "Colorado Springs, CO",
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

        latitude = request.GET.get("lat", "38.8339")
        longitude = request.GET.get("lon", "-104.8214")

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
            "error": True,
            "message": str(e),
        }, status=500)


def fetch_all_events(latitude, longitude):
    """
    Fetch events from all available sources and sort chronologically:
      - Astronomy API: celestial body events
      - Open-Meteo API: astronomical twilight events
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
class CustomUserCreationForm(UserCreationForm):  # pylint: disable=too-many-ancestors
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


def toggle_event_favorite(request):
    try:
        print("RAW POST:", request.POST)

        if not request.user.is_authenticated:
            return JsonResponse(
                {'redirect': '/login/', 'message': 'Please login to add favorites.'},
                status=401
            )

        event_id = request.POST.get("event_id")
        print("EVENT ID RECEIVED:", event_id)

        if not event_id:
            return JsonResponse({"error": "Missing event_id"}, status=400)

        fav = EventFavorite.objects.filter(user=request.user, event_id=event_id).first()
        print("FOUND FAVORITE:", fav)

        if fav:
            fav.delete()
            print("Deleted favorite.")
            return JsonResponse({"favorited": False})

        print("Creating new favorite…")
        created_fav = EventFavorite.objects.create(
            user=request.user,
            event_id=event_id,
            body=request.POST.get("body", ""),
            type=request.POST.get("type", ""),
            peak=request.POST.get("peak", ""),
            rise=request.POST.get("rise", ""),
            transit=request.POST.get("transit", ""),
            set=request.POST.get("set", ""),
        )
        print("Created:", created_fav)

        return JsonResponse({"favorited": True})

    except Exception as e:
        import traceback
        print("ERROR IN toggle_event_favorite:")
        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=500)


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
        system_message = (
            "You are an expert astronomy assistant for CelestiaTrack, a celestial event tracking application. "
            "You help users understand astronomy concepts, celestial events, space phenomena, and answer questions "
            "about planets, stars, galaxies, and the universe. Be informative, engaging, and educational. "
            "Keep responses concise but thorough (2-4 paragraphs maximum unless asked for more detail). "
            "Use scientific accuracy while remaining accessible to general audiences."
        )

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


def weather_api(request):
    """
    API endpoint to fetch weather forecast for a specific location.
    Calculates 'current time' based on the location's UTC offset.
    """
    try:
        lat = request.GET.get("lat", "38.8339")
        lon = request.GET.get("lon", "-104.8214")

        weather_forecast = []

        # Fetch full data (includes 'hourly' and 'utc_offset_seconds')
        data = fetch_weather_forecast(lat, lon)
        raw_hourly = data.get('hourly', {})

        if raw_hourly and 'time' in raw_hourly:
            # 1. Get the offset for this location (e.g., -25200 seconds for MST)
            utc_offset_sec = data.get('utc_offset_seconds', 0)

            # 2. Calculate "Now" at that location
            # Start with current UTC time -> Add the location's offset
            now_utc = datetime.now(timezone.utc)
            current_local_time = now_utc + timedelta(seconds=utc_offset_sec)

            # 3. Format to match API string "YYYY-MM-DDTHH:00"
            current_hour_str = current_local_time.strftime("%Y-%m-%dT%H:00")

            times = raw_hourly.get('time', [])
            covers = raw_hourly.get('cloud_cover', [])
            visibilities = raw_hourly.get('visibility', [])
            precips = raw_hourly.get('precipitation_probability', [])

            for i, t in enumerate(times):
                # Compare the Location's Local Time vs The Forecast Time
                if t >= current_hour_str:
                    weather_forecast.append({
                        'time': t,
                        'cloud_cover': covers[i] if i < len(covers) else 0,
                        'visibility': visibilities[i] if i < len(visibilities) else 0,
                        'precipitation_probability': precips[i] if i < len(precips) else 0,
                    })
                    if len(weather_forecast) >= 12:
                        break

        return JsonResponse({'forecast': weather_forecast})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

def aurora_api(request):
    """API endpoint to get current Aurora status."""
    data = fetch_aurora_data()
    if data:
        return JsonResponse(data)
    return JsonResponse({'error': 'Unavailable'}, status=503)


@login_required
def favorites(request):
    fav_images = Favorite.objects.filter(user=request.user)
    fav_events = EventFavorite.objects.filter(user=request.user).order_by("-saved_at")

    return render(request, "favorites.html", {
        "favorites": fav_images,
        "event_favorites": fav_events
    })


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
    profile, _ = UserProfile.objects.get_or_create(user=user)

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


@login_required
@require_http_methods(["POST"])
def upload_profile_picture(request):
    """Handle profile picture upload via AJAX with cropping support."""
    if request.method != 'POST':
        return JsonResponse({"error": "Only POST requests allowed"}, status=405)
    
    try:
        # Get the uploaded image
        if 'image' not in request.FILES and 'cropped_image' not in request.POST:
            return JsonResponse({"error": "No image provided"}, status=400)
        
        # Handle cropped image (base64 encoded from client-side cropping)
        if 'cropped_image' in request.POST:
            cropped_data = request.POST.get('cropped_image')
            if cropped_data.startswith('data:image'):
                # Remove data URL prefix
                cropped_data = cropped_data.split(',')[1]
            
            # Decode base64 image
            image_data = base64.b64decode(cropped_data)
            image = Image.open(BytesIO(image_data))
        else:
            # Handle regular file upload
            uploaded_file = request.FILES['image']
            image = Image.open(uploaded_file)
        
        # Validate minimum dimensions
        width, height = image.size
        if width < 200 or height < 200:
            return JsonResponse({
                "error": f"Image must be at least 200x200 pixels. Your image is {width}x{height} pixels."
            }, status=400)
        
        # Ensure square format (crop to square if needed)
        if width != height:
            # Crop to square from center
            size = min(width, height)
            left = (width - size) // 2
            top = (height - size) // 2
            right = left + size
            bottom = top + size
            image = image.crop((left, top, right, bottom))
        
        # Resize to ensure minimum 200x200 (but keep square)
        if image.size[0] < 200:
            image = image.resize((200, 200), Image.Resampling.LANCZOS)
        
        # Convert to RGB if necessary (for JPEG compatibility)
        if image.mode in ('RGBA', 'LA', 'P'):
            # Create white background
            rgb_image = Image.new('RGB', image.size, (255, 255, 255))
            if image.mode == 'P':
                image = image.convert('RGBA')
            rgb_image.paste(image, mask=image.split()[-1] if image.mode in ('RGBA', 'LA') else None)
            image = rgb_image
        
        # Save to BytesIO
        output = BytesIO()
        image.save(output, format='JPEG', quality=85)
        output.seek(0)
        
        # Get or create user profile
        profile, created = UserProfile.objects.get_or_create(user=request.user)
        
        # Save the image
        from django.core.files.base import ContentFile
        filename = f"profile_{request.user.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        profile.profile_picture.save(filename, ContentFile(output.read()), save=True)
        
        return JsonResponse({
            "success": True,
            "message": "Profile picture uploaded successfully",
            "image_url": profile.profile_picture.url
        })
        
    except Exception as e:
        import traceback
        print(f"Error uploading profile picture: {e}")
        traceback.print_exc()
        return JsonResponse({
            "error": f"Failed to upload image: {str(e)}"
        }, status=500)


@require_GET
def api_celestial_bodies(request):
    latitude = request.GET.get("lat", 38.8339)
    longitude = request.GET.get("lon", -104.8214)
    data = get_celestial_bodies_with_visibility(latitude, longitude)
    return JsonResponse({"bodies": data}, status=200)


@require_GET
def api_search_city(request):
    """Search city names via Nominatim."""
    query = request.GET.get("q", "")
    if len(query) < 2:
        return JsonResponse({"results": []})

    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={
                "q": query,
                "format": "json",
                "limit": 5,
                "addressdetails": 1,
            },
            headers={"User-Agent": "astral-app/1.0"},
            timeout=10
        )
        data = resp.json()

        results = [
            {
                "name": item.get("display_name"),
                "lat": item.get("lat"),
                "lon": item.get("lon")
            }
            for item in data
        ]
        return JsonResponse({"results": results})

    except Exception as e:
        return JsonResponse({"results": [], "error": str(e)}, status=500)
