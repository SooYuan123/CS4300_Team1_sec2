from django.test import TestCase
from django.urls import reverse
import requests
import requests_mock
from home.utils import fetch_astronomical_events, get_auth_header
from home.views import fetch_all_events

class HomePageTest(TestCase):
    """Tests the basic functionality of the landing page."""

    def test_view_url_exists_at_proper_location(self):
        """Test that the homepage resolves to the root URL (/)."""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)

    def test_view_uses_correct_template(self):
        """Test that the correct template (index.html) is used."""
        response = self.client.get(reverse('index'))
        self.assertTemplateUsed(response, 'index.html')


# --- CONSTANTS FOR MOCKING API ENDPOINTS ---
MOCK_API_BASE = "https://api.astronomyapi.com/api/v2/bodies/events"

SUCCESS_MOON_DATA = {
    "data": {
        "rows": [{
            "body": {"name": "Moon"},
            "events": [{
                "type": "eclipse",
                "eventHighlights": {"peak": {"date": "2025-12-01T10:00:00Z"}},
                "rise": "2025-12-01T05:00:00Z",
                "set": "2025-12-01T15:00:00Z",
                "extraInfo": {"obscuration": 0.5}
            }]
        }]
    }
}


# Helper function to generate mock event data dynamically
def generate_mock_rows(count, body_base_name="Body"):
    """Generates a list of rows with unique event data for mocking."""
    rows = []
    for i in range(count):
        row = {
            "body": {"name": f"{body_base_name} {i + 1}"},
            "events": [{
                "type": "E",
                # Create unique dates for reliable sorting tests
                "eventHighlights": {"peak": {"date": f"2025-12-{str(i + 1).zfill(2)}T10:00:00Z"}},
            }]
        }
        rows.append(row)
    return rows


class UtilityFunctionTests(TestCase):
    """Tests the complex logic in home/utils.py to achieve high coverage."""

    def test_fetch_astronomical_events_success(self):
        """Test successful API call returns structured data."""
        with requests_mock.Mocker() as m:
            m.get(f"{MOCK_API_BASE}/moon", json=SUCCESS_MOON_DATA, status_code=200)
            result = fetch_astronomical_events("moon", "38.77", "-84.39")
            self.assertTrue(isinstance(result, list))
            self.assertEqual(result[0]["body"]["name"], "Moon")

    def test_fetch_astronomical_events_404_handling(self):
        """Test function handles 404 error gracefully."""
        with requests_mock.Mocker() as m:
            m.get(f"{MOCK_API_BASE}/pluto", status_code=404)
            result = fetch_astronomical_events("pluto", "38.77", "-84.39")
            self.assertEqual(result, [])

    def test_fetch_astronomical_events_403_failure(self):
        """Test function raises an exception on a critical API failure (like 403 Forbidden)."""
        with requests_mock.Mocker() as m:
            m.get(f"{MOCK_API_BASE}/sun", status_code=403)
            with self.assertRaises(requests.HTTPError):
                fetch_astronomical_events("sun", "38.77", "-84.39")

    def test_fetch_all_events_sorting_and_aggregation(self):
        """Test that fetch_all_events aggregates data and sorts by date."""
        with requests_mock.Mocker() as m:
            # Mock success for Sun (Later date) and Moon (Earlier date)
            m.get(f"{MOCK_API_BASE}/sun", json={
                "data": {"rows": [{"body": {"name": "Sun"}, "events": [
                    {"type": "Solar", "eventHighlights": {"peak": {"date": "2025-12-05T10:00:00Z"}}}]}]}
            }, status_code=200)
            m.get(f"{MOCK_API_BASE}/moon", json={
                "data": {"rows": [{"body": {"name": "Moon"}, "events": [
                    {"type": "Lunar", "eventHighlights": {"peak": {"date": "2025-12-01T10:00:00Z"}}}]}]}
            }, status_code=200)

            # Mock 404 for all other planets (ensures try/except in fetch_all_events is covered)
            for body in ["mercury", "venus", "mars", "jupiter", "saturn", "uranus", "neptune", "pluto"]:
                m.get(requests_mock.ANY, status_code=404)

            events = fetch_all_events("38.77", "-84.39")

            # Assert aggregation and sorting by date
            self.assertTrue(len(events) >= 2)
            self.assertEqual(events[0]["body"], "Moon") # Earliest event first
            self.assertEqual(events[1]["body"], "Sun")  # Later event second


class ViewTests(TestCase):
    """Tests for the primary view functions in home/views.py (index, events_list, events_api)"""

    def test_index_view_loads(self):
        """Test the main index page (/) loads correctly."""
        response = self.client.get(reverse('index'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'index.html')

    def test_events_list_view_success_and_pagination_logic(self):
        """Test the main events_list view loads and correctly handles pagination logic."""
        with requests_mock.Mocker() as m:
            # Generate 40 unique events (ensures we have > 20 events for has_more=True check)
            mock_rows = generate_mock_rows(40)
            mock_data = {"data": {"rows": mock_rows}}

            # Mock ALL requests to return the 30 events
            m.get(requests_mock.ANY, json=mock_data, status_code=200)

            response = self.client.get(reverse('events_list'))

            self.assertEqual(response.status_code, 200)
            self.assertTemplateUsed(response, 'events_list.html')

            # Assert initial events loaded (first 20) and pagination flag (has_more)
            self.assertEqual(len(response.context['events']), 20)
            self.assertTrue(response.context['has_more'])

    def test_events_list_view_failure_handling(self):
        """Test events_list gracefully handles a catastrophic API failure."""
        with requests_mock.Mocker() as m:
            m.get(requests_mock.ANY, status_code=403)
            response = self.client.get(reverse('events_list'))

            self.assertEqual(response.status_code, 200)
            self.assertTemplateUsed(response, 'events_list.html')
            self.assertEqual(len(response.context['events']), 0)
            self.assertFalse(response.context['has_more'])

    def test_events_api_endpoint_success_and_lazy_loading(self):
        """Test the events_api endpoint handles offset/limit parameters correctly."""
        with requests_mock.Mocker() as m:
            mock_rows = generate_mock_rows(30)
            mock_data = {"data": {"rows": mock_rows}}
            m.get(requests_mock.ANY, json=mock_data, status_code=200)

            # Request the next slice (offset=20, limit=10)
            response = self.client.get(reverse('events_api'), {'offset': 20, 'limit': 10})
            data = response.json()

            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(data['events']), 10)  # Should retrieve 10 events (21st to 30th)
            self.assertFalse(data['has_more'])  # Should be the last slice

    def test_events_api_endpoint_failure_handling(self):
        """Test the events_api endpoint returns JSON error on catastrophic failure."""
        with requests_mock.Mocker() as m:
            m.get(requests_mock.ANY, status_code=403)

            response = self.client.get(reverse('events_api'))
            data = response.json()

            self.assertEqual(response.status_code, 500)
            self.assertEqual(len(data['events']), 0)
            self.assertTrue(data['error'])
