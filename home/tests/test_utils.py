from django.test import TestCase
import requests
import requests_mock
from home.utils import fetch_astronomical_events
from home.views import fetch_all_events


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


def generate_mock_rows(count, body_base_name="Body"):
    rows = []
    for i in range(count):
        row = {
            "body": {"name": f"{body_base_name} {i + 1}"},
            "events": [{
                "type": "E",
                "eventHighlights": {"peak": {"date": f"2025-12-{str(i + 1).zfill(2)}T10:00:00Z"}}
            }]
        }
        rows.append(row)
    return rows


class UtilityFunctionTests(TestCase):
    """Tests the logic in home/utils.py."""

    def test_fetch_astronomical_events_success(self):
        with requests_mock.Mocker() as m:
            with self.settings(ASTRONOMY_API_APP_ID='test_id', ASTRONOMY_API_APP_SECRET='test_secret'):
                m.get(f"{MOCK_API_BASE}/moon", json=SUCCESS_MOON_DATA, status_code=200)
                result = fetch_astronomical_events("moon", "38.775867", "-84.39733")
                self.assertTrue(isinstance(result, list))
                self.assertEqual(result[0]["body"]["name"], "Moon")

    def test_fetch_astronomical_events_404_handling(self):
        with requests_mock.Mocker() as m:
            m.get(f"{MOCK_API_BASE}/pluto", status_code=404)
            result = fetch_astronomical_events("pluto", "38.775867", "-84.39733")
            self.assertEqual(result, [])

    def test_fetch_astronomical_events_403_failure(self):
        with requests_mock.Mocker() as m:
            m.get(f"{MOCK_API_BASE}/sun", status_code=403)
            with self.assertRaises(requests.HTTPError):
                fetch_astronomical_events("sun", "38.775867", "-84.39733")

    def test_fetch_all_events_sorting_and_aggregation(self):
        with requests_mock.Mocker() as m:
            with self.settings(ASTRONOMY_API_APP_ID='test_id', ASTRONOMY_API_APP_SECRET='test_secret'):
                m.get(f"{MOCK_API_BASE}/sun", json={"data": {"rows": generate_mock_rows(1, "Sun")}}, status_code=200)
                m.get(f"{MOCK_API_BASE}/moon", json={"data": {"rows": generate_mock_rows(1, "Moon")}}, status_code=200)
                events = fetch_all_events("38.775867", "-84.39733")
                self.assertTrue(len(events) >= 2)
                self.assertEqual(events[0]["body"], "Moon")
                self.assertEqual(events[1]["body"], "Sun")
