"""
Tests for Aurora Forecast functionality (Utils and Views).
"""
import pytest
import requests_mock
from django.urls import reverse
from home.utils import fetch_aurora_data


def test_fetch_aurora_data_success():
    """Test successful fetching and parsing of NOAA data."""
    # NOAA returns a list of lists. First row is header, last row is latest data.
    mock_response = [
        ["time_tag", "planetary_k_index", "dst_flag"],
        ["2025-12-09 00:00:00", "2.33", "0"]
    ]

    with requests_mock.Mocker() as mocker:
        mocker.get(
            "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json",
            json=mock_response,
            status_code=200
        )

        data = fetch_aurora_data()

        assert data is not None
        assert data['kp_index'] == 2.33
        assert data['status'] == "Low"
        assert data['color'] == "success"


def test_fetch_aurora_data_storm_level():
    """Test logic for high Kp index (Storm level)."""
    mock_response = [
        ["time_tag", "planetary_k_index", "dst_flag"],
        ["2025-12-09 00:00:00", "6.67", "0"]
    ]

    with requests_mock.Mocker() as mocker:
        mocker.get(
            "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json",
            json=mock_response
        )

        data = fetch_aurora_data()

        assert data['kp_index'] == 6.67
        assert "Storm" in data['status']
        assert data['color'] == "danger"


def test_fetch_aurora_api_failure():
    """Test graceful handling of API timeout/error."""
    with requests_mock.Mocker() as mocker:
        mocker.get(
            "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json",
            exc=Exception("Connection Timeout")
        )

        data = fetch_aurora_data()
        assert data is None


@pytest.mark.django_db
def test_aurora_view_endpoint(client):
    """Test the Django View integration."""
    mock_response = [
        ["time_tag", "planetary_k_index"],
        ["2025-12-09 00:00:00", "3.00"]
    ]

    with requests_mock.Mocker() as mocker:
        mocker.get(
            "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json",
            json=mock_response
        )

        # Use the name of the url from urls.py
        response = client.get(reverse('aurora_api'))

        assert response.status_code == 200
        json_data = response.json()
        assert json_data['kp_index'] == 3.0
