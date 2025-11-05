from django.conf import settings
import base64
import requests

def astronomy_get(url, params=None):
    if not settings.ASTRONOMY_API_APP_ID or not settings.ASTRONOMY_API_APP_SECRET:
        raise RuntimeError("AstronomyAPI credentials are not set")
    token = base64.b64encode(
        f"{settings.ASTRONOMY_API_APP_ID}:{settings.ASTRONOMY_API_APP_SECRET}".encode()
    ).decode()
    headers = {
        "Authorization": f"Basic {token}",
        "Content-Type": "application/json",
    }
    r = requests.get(url, params=params or {}, headers=headers, timeout=20)
    r.raise_for_status()
    return r.json()
