from django.test import TestCase
from django.urls import reverse
import requests_mock
from datetime import date
from home.views import get_apod_for_date
import pytest
from django.contrib.auth.models import User

def generate_mock_rows(count):
    return [{
        "body": {"name": f"Body {i+1}"},
        "events": [{"type": "E", "eventHighlights": {"peak": {"date": f"2025-12-{i+1:02d}T10:00:00Z"}}}]
    } for i in range(count)]


class ViewTests(TestCase):
    """Tests for primary views in home/views.py."""

    def test_events_list_view_failure_handling(self):
        with requests_mock.Mocker() as m:
            m.get(requests_mock.ANY, status_code=403)
            response = self.client.get(reverse('events_list'))
            self.assertEqual(response.status_code, 200)
            self.assertTemplateUsed(response, 'events_list.html')
            self.assertEqual(len(response.context['events']), 0)
            self.assertFalse(response.context['has_more'])

    def test_events_api_endpoint_success_and_lazy_loading(self):
        with requests_mock.Mocker() as m:
            mock_rows = generate_mock_rows(30)
            m.get(requests_mock.ANY, json={"data": {"rows": mock_rows}}, status_code=200)
            response = self.client.get(reverse('events_api'), {'offset': 20, 'limit': 10})
            data = response.json()
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(data['events']), 10)
            self.assertFalse(data['has_more'])

    def test_events_api_endpoint_failure_handling(self):
        with requests_mock.Mocker() as m:
            with self.settings(ASTRONOMY_API_APP_ID='test_id', ASTRONOMY_API_APP_SECRET='test_secret'):
                m.get(requests_mock.ANY, status_code=403)
                response = self.client.get(reverse('events_api'))
                data = response.json()
                self.assertEqual(response.status_code, 500)
                self.assertEqual(len(data['events']), 0)
                self.assertTrue(data['error'])

def test_index_view_success(monkeypatch, client):
    # Patch APOD fetch to return a sample dict
    monkeypatch.setattr("home.views.find_most_recent_apod", lambda: {"title":"Test Apod"})
    response = client.get(reverse("index"))
    assert response.status_code == 200
    assert response.context["apod"]["title"] == "Test Apod"

def test_get_apod_for_date_no_key(monkeypatch):
    monkeypatch.setattr("home.views.NASA_API_KEY", None)
    d = date.today()
    assert get_apod_for_date(d) is None

@pytest.mark.django_db
def test_register_get(client):
    response = client.get(reverse("register"))
    assert response.status_code == 200
    assert "form" in response.context

@pytest.mark.django_db
def test_register_post_success(client):
    response = client.post(reverse("register"), {"username":"newuser","password1":"strongpass123","password2":"strongpass123"})
    assert response.status_code == 302  # redirect
    assert User.objects.filter(username="newuser").exists()

@pytest.mark.django_db
def test_register_post_invalid(client):
    response = client.post(reverse("register"), {"username":"", "password1":"a", "password2":"b"})
    assert response.status_code == 200
    assert "form" in response.context