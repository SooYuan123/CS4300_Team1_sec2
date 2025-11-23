import pytest
from django.urls import reverse
from django.contrib.auth.models import User
from home.models import EventFavorite
from unittest.mock import patch


@pytest.mark.django_db
def test_favorite_event_requires_login(client):
    url = reverse("toggle_event_favorite")
    res = client.post(url, {"event_id": "Sun_Rise_2025"})
    assert res.status_code == 401

@pytest.mark.django_db
def test_favorite_event_add_and_remove(client):
    user = User.objects.create_user("y", password="pass")
    client.login(username="y", password="pass")

    url = reverse("toggle_event_favorite")
    data = {
        "event_id": "Sun_Rise_2025",
        "body": "Sun",
        "type": "Rise",
        "peak": "2025-01-01T06:00:00",
        "rise": "2025-01-01T06:00:00",
        "transit": "",
        "set": "",
    }

    # Add
    res = client.post(url, data)
    assert res.status_code == 200
    assert EventFavorite.objects.count() == 1

    # Remove
    res = client.post(url, data)
    assert EventFavorite.objects.count() == 0

@pytest.mark.django_db
def test_event_favorite_unauth_redirects(client):
    url = reverse("toggle_event_favorite")
    res = client.post(url, {"event_id": "X"})
    assert res.status_code == 401
    assert res.json()["redirect"] == "/login/"

