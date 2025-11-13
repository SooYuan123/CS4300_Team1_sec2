from django.test import TestCase
from django.urls import reverse
import requests_mock
from datetime import date
from home.views import (
    get_apod_for_date, get_jwst_random_image, get_jwst_recent_images,
    _parse_iso, _earliest_peak_from_events, fetch_all_events
)
import pytest
from django.contrib.auth.models import User
from unittest.mock import patch, MagicMock


def generate_mock_rows(count):
    return [{
        "body": {"name": f"Body {i + 1}"},
        "events": [{"type": "E", "eventHighlights": {"peak": {"date": f"2025-12-{i + 1:02d}T10:00:00Z"}}}]
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

    def test_events_list_view_success(self):
        """Test events list with successful API response."""
        with requests_mock.Mocker() as m:
            mock_rows = generate_mock_rows(25)
            m.get(requests_mock.ANY, json={"data": {"rows": mock_rows}}, status_code=200)
            response = self.client.get(reverse('events_list'))

            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.context['events']), 20)
            self.assertTrue(response.context['has_more'])

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


class GalleryTests(TestCase):
    """Tests for gallery view."""

    def setUp(self):
        """Create a test user for login-required tests."""
        self.user = User.objects.create_user(username='testuser', password='testpass123')

    def test_gallery_with_nasa_images_success(self):
        """Test gallery successfully loads NASA images with all data fields."""
        self.client.login(username='testuser', password='testpass123')

        mock_nasa_response = {
            'collection': {
                'items': [
                    {
                        'links': [{'href': 'https://example.com/img1.jpg'}],
                        'data': [{'title': 'Test Image 1', 'description': 'Test desc 1'}]
                    },
                    {
                        'links': [{'href': 'https://example.com/img2.jpg'}],
                        'data': [{'title': 'Test Image 2', 'description': 'Test desc 2'}]
                    }
                ]
            }
        }

        with requests_mock.Mocker() as m:
            m.get('https://images-api.nasa.gov/search', json=mock_nasa_response, status_code=200)
            response = self.client.get(reverse('gallery'))

            self.assertEqual(response.status_code, 200)
            self.assertIn('images', response.context)
            self.assertEqual(len(response.context['images']), 2)
            # Check that all fields are populated
            self.assertEqual(response.context['images'][0]['src'], 'https://example.com/img1.jpg')
            self.assertEqual(response.context['images'][0]['title'], 'Test Image 1')

    def test_gallery_nasa_api_failure_fallback(self):
        """Test gallery falls back to static images when NASA API fails."""
        self.client.login(username='testuser', password='testpass123')

        with requests_mock.Mocker() as m:
            m.get('https://images-api.nasa.gov/search', exc=Exception('Connection error'))
            response = self.client.get(reverse('gallery'))

            self.assertEqual(response.status_code, 200)
            self.assertIn('images', response.context)
            # Should have 6 fallback images
            self.assertEqual(len(response.context['images']), 6)

    def test_gallery_with_missing_links(self):
        """Test gallery handles items with missing links."""
        self.client.login(username='testuser', password='testpass123')

        mock_nasa_response = {
            'collection': {
                'items': [
                    {
                        'links': [],  # Empty links
                        'data': [{'title': 'Test Image 1'}]
                    },
                    {
                        'links': [{'href': 'https://example.com/img2.jpg'}],
                        'data': [{'title': 'Test Image 2', 'description': 'Valid'}]
                    }
                ]
            }
        }

        with requests_mock.Mocker() as m:
            m.get('https://images-api.nasa.gov/search', json=mock_nasa_response, status_code=200)
            response = self.client.get(reverse('gallery'))

            self.assertEqual(response.status_code, 200)
            # Should only have 1 valid image
            self.assertEqual(len(response.context['images']), 1)


class JWSTAPITests(TestCase):
    """Tests for JWST API integration."""

    @patch('home.views.JWST_API_KEY', 'test_key_123')
    def test_get_jwst_random_image_success(self):
        """Test successful JWST image fetch."""
        mock_response = {
            'statusCode': 200,
            'body': [{
                'id': 'test_image.jpg',
                'observation_id': 'jw12345',
                'program': 1234,
                'details': {
                    'mission': 'JWST',
                    'instruments': [{'instrument': 'NIRCam'}],
                    'description': 'Test image'
                },
                'file_type': 'jpg',
                'location': 'https://example.com/test.jpg'
            }]
        }

        with requests_mock.Mocker() as m:
            m.get('https://api.jwstapi.com/all/type/jpg', json=mock_response, status_code=200)
            result = get_jwst_random_image()

            self.assertIsNotNone(result)
            self.assertEqual(result['observation_id'], 'jw12345')

    @patch('home.views.JWST_API_KEY', None)
    def test_get_jwst_random_image_no_key(self):
        """Test JWST fetch with no API key."""
        result = get_jwst_random_image()
        self.assertIsNone(result)

    @patch('home.views.JWST_API_KEY', 'test_key_123')
    def test_get_jwst_random_image_api_failure(self):
        """Test JWST fetch when API returns error."""
        with requests_mock.Mocker() as m:
            m.get('https://api.jwstapi.com/all/type/jpg', status_code=404)
            result = get_jwst_random_image()
            self.assertIsNone(result)

    @patch('home.views.JWST_API_KEY', 'test_key_123')
    @patch('home.views.requests.get')
    def test_get_jwst_random_image_request_exception(self, mock_get):
        """Test JWST fetch with request exception."""
        import requests
        mock_get.side_effect = requests.RequestException('Network error')
        result = get_jwst_random_image()
        self.assertIsNone(result)

    @patch('home.views.JWST_API_KEY', 'test_key_123')
    def test_get_jwst_recent_images_success_list(self):
        """Test fetching recent JWST images with list response."""
        mock_response = [
            {'id': 'img1.jpg', 'location': 'url1'},
            {'id': 'img2.jpg', 'location': 'url2'}
        ]

        with requests_mock.Mocker() as m:
            m.get(requests_mock.ANY, json=mock_response, status_code=200)
            result = get_jwst_recent_images(count=2)

            self.assertIsNotNone(result)
            self.assertEqual(len(result), 2)

    @patch('home.views.JWST_API_KEY', 'test_key_123')
    def test_get_jwst_recent_images_success_dict(self):
        """Test fetching recent JWST images with dict response."""
        mock_response = {
            'body': [
                {'id': 'img1.jpg', 'location': 'url1'},
                {'id': 'img2.jpg', 'location': 'url2'}
            ]
        }

        with requests_mock.Mocker() as m:
            m.get(requests_mock.ANY, json=mock_response, status_code=200)
            result = get_jwst_recent_images(count=2)

            self.assertIsNotNone(result)
            self.assertEqual(len(result), 2)

    @patch('home.views.JWST_API_KEY', None)
    def test_get_jwst_recent_images_no_key(self):
        """Test recent images with no API key."""
        result = get_jwst_recent_images()
        self.assertIsNone(result)

    @patch('home.views.JWST_API_KEY', 'test_key_123')
    def test_get_jwst_recent_images_api_error(self):
        """Test recent images with API error."""
        with requests_mock.Mocker() as m:
            m.get(requests_mock.ANY, status_code=500)
            result = get_jwst_recent_images()
            self.assertIsNone(result)

    @patch('home.views.JWST_API_KEY', 'test_key_123')
    @patch('home.views.requests.get')
    def test_get_jwst_recent_images_request_exception(self, mock_get):
        """Test recent images with request exception."""
        import requests
        mock_get.side_effect = requests.RequestException('Network error')
        result = get_jwst_recent_images()
        self.assertIsNone(result)

    @patch('home.views.JWST_API_KEY', 'test_key_123')
    def test_index_view_with_jwst(self):
        """Test index view using JWST API."""
        mock_jwst_data = {
            'id': 'test.jpg',
            'observation_id': 'jw12345',
            'program': 1234,
            'details': {'description': 'Test'},
            'location': 'https://example.com/test.jpg'
        }

        with patch('home.views.get_jwst_random_image', return_value=mock_jwst_data):
            response = self.client.get(reverse('index'))

            self.assertEqual(response.status_code, 200)
            self.assertIn('space_image', response.context)

    @patch('home.views.JWST_API_KEY', 'test_key_123')
    def test_index_view_jwst_fallback_to_nasa(self):
        """Test index view falls back to NASA when JWST fails."""
        mock_nasa_data = {
            'title': 'NASA Test',
            'url': 'https://example.com/nasa.jpg'
        }

        with patch('home.views.get_jwst_random_image', return_value=None):
            with patch('home.views.find_most_recent_apod', return_value=mock_nasa_data):
                response = self.client.get(reverse('index'))

                self.assertEqual(response.status_code, 200)
                self.assertIn('space_image', response.context)

    def test_index_view_exception_handling(self):
        """Test index view handles exceptions gracefully."""
        with patch('home.views.get_jwst_random_image', side_effect=Exception('Test error')):
            response = self.client.get(reverse('index'))

            self.assertEqual(response.status_code, 200)


class APODFunctionTests(TestCase):
    """Tests for NASA APOD helper functions."""

    @patch('home.views.NASA_API_KEY', 'test_nasa_key')
    def test_get_apod_for_date_success(self):
        """Test successful APOD fetch for specific date."""
        mock_apod = {
            'title': 'Test APOD',
            'url': 'https://example.com/apod.jpg',
            'date': '2025-11-05'
        }

        with requests_mock.Mocker() as m:
            m.get('https://api.nasa.gov/planetary/apod', json=mock_apod, status_code=200)
            result = get_apod_for_date(date(2025, 11, 5))

            self.assertIsNotNone(result)
            self.assertEqual(result['title'], 'Test APOD')

    @patch('home.views.NASA_API_KEY', None)
    def test_get_apod_for_date_no_key(self):
        """Test APOD fetch with no API key."""
        result = get_apod_for_date(date(2025, 11, 5))
        self.assertIsNone(result)

    @patch('home.views.NASA_API_KEY', 'test_nasa_key')
    def test_get_apod_for_date_api_error(self):
        """Test APOD fetch when API returns non-200 status."""
        with requests_mock.Mocker() as m:
            m.get('https://api.nasa.gov/planetary/apod', status_code=404)
            result = get_apod_for_date(date(2025, 11, 5))

            self.assertIsNone(result)

    @patch('home.views.NASA_API_KEY', 'test_nasa_key')
    @patch('home.views.requests.get')
    def test_get_apod_for_date_request_exception(self, mock_get):
        """Test APOD fetch with request exception."""
        import requests
        mock_get.side_effect = requests.RequestException('Network error')
        result = get_apod_for_date(date(2025, 11, 5))
        self.assertIsNone(result)

    @patch('home.views.NASA_API_KEY', 'test_nasa_key')
    @patch('home.views.get_apod_for_date')
    def test_find_most_recent_apod_first_try_success(self, mock_get_apod):
        """Test finding APOD succeeds on first try."""
        mock_get_apod.return_value = {'title': 'Recent APOD'}

        from home.views import find_most_recent_apod
        result = find_most_recent_apod()

        self.assertIsNotNone(result)
        self.assertEqual(result['title'], 'Recent APOD')

    @patch('home.views.NASA_API_KEY', 'test_nasa_key')
    @patch('home.views.get_apod_for_date')
    def test_find_most_recent_apod_all_fail(self, mock_get_apod):
        """Test when all APOD attempts fail."""
        mock_get_apod.return_value = None

        from home.views import find_most_recent_apod
        result = find_most_recent_apod(max_days_back=5)

        self.assertIsNone(result)


class HelperFunctionTests(TestCase):
    """Tests for helper functions in views."""

    def test_parse_iso_valid_date_with_z(self):
        """Test parsing valid ISO date string with Z."""
        result = _parse_iso("2025-11-05T10:00:00Z")
        self.assertIsNotNone(result)
        self.assertEqual(result.year, 2025)

    def test_parse_iso_none(self):
        """Test parsing None."""
        result = _parse_iso(None)
        self.assertIsNone(result)

    def test_parse_iso_invalid_format(self):
        """Test parsing invalid date string."""
        result = _parse_iso("not-a-date")
        self.assertIsNone(result)

    def test_earliest_peak_from_events_with_peaks(self):
        """Test finding earliest peak from events."""
        events = [
            {'eventHighlights': {'peak': {'date': '2025-12-25T10:00:00Z'}}},
            {'eventHighlights': {'peak': {'date': '2025-11-15T10:00:00Z'}}}
        ]

        result = _earliest_peak_from_events(events)
        self.assertIsNotNone(result)
        self.assertIn('2025-11-15', result)

    def test_earliest_peak_from_events_empty(self):
        """Test with empty events list."""
        result = _earliest_peak_from_events([])
        self.assertIsNone(result)

    def test_earliest_peak_from_events_no_peaks(self):
        """Test with events that have no peaks."""
        events = [{'eventHighlights': {}}]
        result = _earliest_peak_from_events(events)
        self.assertIsNone(result)

    def test_earliest_peak_with_utc_timezone(self):
        """Test earliest peak returns Z format for UTC."""
        events = [{'eventHighlights': {'peak': {'date': '2025-11-15T10:00:00+00:00'}}}]
        result = _earliest_peak_from_events(events)
        self.assertIsNotNone(result)


class RegisterTests(TestCase):
    """Tests for register view."""

    def test_register_post_success(self):
        """Test successful registration."""
        response = self.client.post(reverse('register'), {
            'username': 'newuser',
            'password1': 'strongpass123',
            'password2': 'strongpass123'
        })

        self.assertEqual(response.status_code, 302)  # Redirect
        self.assertTrue(User.objects.filter(username='newuser').exists())

    def test_register_post_invalid(self):
        """Test registration with invalid data."""
        response = self.client.post(reverse('register'), {
            'username': '',
            'password1': 'a',
            'password2': 'b'
        })

        self.assertEqual(response.status_code, 200)
        self.assertIn('form', response.context)

    def test_register_get(self):
        """Test GET request to register page."""
        response = self.client.get(reverse('register'))

        self.assertEqual(response.status_code, 200)
        self.assertIn('form', response.context)


# Pytest-style tests
def test_index_view_success(monkeypatch, client):
    monkeypatch.setattr("home.views.find_most_recent_apod", lambda: {"title": "Test Apod"})
    monkeypatch.setattr("home.views.get_jwst_random_image", lambda: None)
    response = client.get(reverse("index"))
    assert response.status_code == 200


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
    response = client.post(reverse("register"),
                           {"username": "newuser", "password1": "strongpass123", "password2": "strongpass123"})
    assert response.status_code == 302
    assert User.objects.filter(username="newuser").exists()


@pytest.mark.django_db
def test_register_post_invalid(client):
    response = client.post(reverse("register"), {"username": "", "password1": "a", "password2": "b"})
    assert response.status_code == 200
    assert "form" in response.context