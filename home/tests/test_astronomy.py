from django.test import TestCase
from django.conf import settings
import requests_mock
from unittest.mock import patch
from home.astronomy import astronomy_get


class AstronomyAPITests(TestCase):
    """Tests for astronomy.py helper functions."""

    @patch.object(settings, 'ASTRONOMY_API_APP_ID', 'test_id')
    @patch.object(settings, 'ASTRONOMY_API_APP_SECRET', 'test_secret')
    def test_astronomy_get_success(self):
        """Test successful API call with authentication."""
        test_url = "https://api.astronomyapi.com/api/v2/test"
        mock_response = {"data": {"result": "success"}}

        with requests_mock.Mocker() as m:
            m.get(test_url, json=mock_response, status_code=200)

            result = astronomy_get(test_url)

            self.assertEqual(result, mock_response)
            # Verify the request was made with correct headers
            self.assertIn('Authorization', m.last_request.headers)
            self.assertTrue(m.last_request.headers['Authorization'].startswith('Basic '))

    @patch.object(settings, 'ASTRONOMY_API_APP_ID', 'test_id')
    @patch.object(settings, 'ASTRONOMY_API_APP_SECRET', 'test_secret')
    def test_astronomy_get_with_params(self):
        """Test API call with query parameters."""
        test_url = "https://api.astronomyapi.com/api/v2/bodies/positions"
        test_params = {"latitude": "40.7128", "longitude": "-74.0060"}
        mock_response = {"data": {"positions": []}}

        with requests_mock.Mocker() as m:
            m.get(test_url, json=mock_response, status_code=200)

            result = astronomy_get(test_url, params=test_params)

            self.assertEqual(result, mock_response)
            # Verify params were passed
            self.assertEqual(m.last_request.qs['latitude'][0], '40.7128')
            self.assertEqual(m.last_request.qs['longitude'][0], '-74.0060')

    @patch.object(settings, 'ASTRONOMY_API_APP_ID', None)
    @patch.object(settings, 'ASTRONOMY_API_APP_SECRET', 'test_secret')
    def test_astronomy_get_missing_app_id(self):
        """Test that missing APP_ID raises RuntimeError."""
        test_url = "https://api.astronomyapi.com/api/v2/test"

        with self.assertRaises(RuntimeError) as context:
            astronomy_get(test_url)

        self.assertIn("credentials are not set", str(context.exception))

    @patch.object(settings, 'ASTRONOMY_API_APP_ID', 'test_id')
    @patch.object(settings, 'ASTRONOMY_API_APP_SECRET', None)
    def test_astronomy_get_missing_app_secret(self):
        """Test that missing APP_SECRET raises RuntimeError."""
        test_url = "https://api.astronomyapi.com/api/v2/test"

        with self.assertRaises(RuntimeError) as context:
            astronomy_get(test_url)

        self.assertIn("credentials are not set", str(context.exception))

    @patch.object(settings, 'ASTRONOMY_API_APP_ID', None)
    @patch.object(settings, 'ASTRONOMY_API_APP_SECRET', None)
    def test_astronomy_get_missing_both_credentials(self):
        """Test that missing both credentials raises RuntimeError."""
        test_url = "https://api.astronomyapi.com/api/v2/test"

        with self.assertRaises(RuntimeError) as context:
            astronomy_get(test_url)

        self.assertIn("credentials are not set", str(context.exception))

    @patch.object(settings, 'ASTRONOMY_API_APP_ID', 'test_id')
    @patch.object(settings, 'ASTRONOMY_API_APP_SECRET', 'test_secret')
    def test_astronomy_get_http_error(self):
        """Test that HTTP errors are raised."""
        test_url = "https://api.astronomyapi.com/api/v2/test"

        with requests_mock.Mocker() as m:
            m.get(test_url, status_code=403)

            with self.assertRaises(Exception):  # requests.HTTPError
                astronomy_get(test_url)

    @patch.object(settings, 'ASTRONOMY_API_APP_ID', 'test_id')
    @patch.object(settings, 'ASTRONOMY_API_APP_SECRET', 'test_secret')
    def test_astronomy_get_network_error(self):
        """Test that network errors are raised."""
        test_url = "https://api.astronomyapi.com/api/v2/test"

        with requests_mock.Mocker() as m:
            m.get(test_url, exc=ConnectionError('Network failure'))

            with self.assertRaises(ConnectionError):
                astronomy_get(test_url)

    @patch.object(settings, 'ASTRONOMY_API_APP_ID', 'test_id')
    @patch.object(settings, 'ASTRONOMY_API_APP_SECRET', 'test_secret')
    def test_astronomy_get_creates_correct_auth_header(self):
        """Test that Basic auth header is correctly formatted."""
        import base64

        test_url = "https://api.astronomyapi.com/api/v2/test"
        mock_response = {"status": "ok"}

        with requests_mock.Mocker() as m:
            m.get(test_url, json=mock_response, status_code=200)

            astronomy_get(test_url)

            # Verify the auth header format
            auth_header = m.last_request.headers['Authorization']
            self.assertTrue(auth_header.startswith('Basic '))

            # Decode and verify credentials
            encoded_creds = auth_header.replace('Basic ', '')
            decoded_creds = base64.b64decode(encoded_creds).decode()
            self.assertEqual(decoded_creds, 'test_id:test_secret')

    @patch.object(settings, 'ASTRONOMY_API_APP_ID', 'test_id')
    @patch.object(settings, 'ASTRONOMY_API_APP_SECRET', 'test_secret')
    def test_astronomy_get_sets_content_type_header(self):
        """Test that Content-Type header is set correctly."""
        test_url = "https://api.astronomyapi.com/api/v2/test"
        mock_response = {"status": "ok"}

        with requests_mock.Mocker() as m:
            m.get(test_url, json=mock_response, status_code=200)

            astronomy_get(test_url)

            self.assertEqual(
                m.last_request.headers['Content-Type'],
                'application/json'
            )
