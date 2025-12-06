import pytest
import requests
import requests_mock
from datetime import datetime, timezone
from django.conf import settings
from home import utils


# -------------------------------------------------------------------
# BASIC AUTH TESTS
# -------------------------------------------------------------------

def test_get_auth_header_with_creds(settings):
    settings.ASTRONOMY_API_APP_ID = "abc"
    settings.ASTRONOMY_API_APP_SECRET = "123"
    header = utils.get_auth_header()
    assert "Authorization" in header
    assert header["Authorization"].startswith("Basic ")


def test_get_radiant_drift_auth_header_success(settings):
    settings.RADIANT_DRIFT_API_KEY = "TESTKEY"
    header = utils.get_radiant_drift_auth_header()
    assert header == {"Authorization": "RadiantDriftAuth TESTKEY"}


def test_get_solar_system_auth_header(settings):
    settings.SSOD_APP_ID = "XYZ"
    assert utils.get_solar_system_auth_header() == {"Authorization": "Bearer XYZ"}


# -------------------------------------------------------------------
# fetch_astronomical_events
# -------------------------------------------------------------------

@pytest.mark.django_db
def test_fetch_astronomical_events_success(settings):
    settings.ASTRONOMY_API_APP_ID = "id"
    settings.ASTRONOMY_API_APP_SECRET = "secret"

    payload = {"data": {"rows": [{"body": {"name": "Moon"}}]}}
    with requests_mock.Mocker() as m:
        m.get(utils.ASTRONOMY_API_BASE + "/moon", json=payload, status_code=200)
        rows = utils.fetch_astronomical_events("moon", 1, 2)
        assert rows[0]["body"]["name"] == "Moon"


@pytest.mark.django_db
def test_fetch_astronomical_events_404():
    with requests_mock.Mocker() as m:
        m.get(utils.ASTRONOMY_API_BASE + "/x", status_code=404)
        assert utils.fetch_astronomical_events("x", 1, 2) == []


@pytest.mark.django_db
def test_fetch_astronomical_events_403_raises():
    with requests_mock.Mocker() as m:
        m.get(utils.ASTRONOMY_API_BASE + "/sun", status_code=403)
        with pytest.raises(requests.HTTPError):
            utils.fetch_astronomical_events("sun", 1, 2)


@pytest.mark.django_db
def test_fetch_astronomical_events_request_error(monkeypatch):
    def bad_get(*args, **kwargs):
        raise requests.RequestException("Boom")
    monkeypatch.setattr(requests, "get", bad_get)

    assert utils.fetch_astronomical_events("moon", 1, 2) == []


# -------------------------------------------------------------------
# fetch_rise_set_times
# -------------------------------------------------------------------

@pytest.mark.django_db
def test_fetch_rise_set_times_success(settings):
    settings.RADIANT_DRIFT_API_KEY = "KEY"
    payload = {
        "response": {
            "2025-01-01": {
                "sun": {"rise": {"utc": "2025-01-01T06:00:00Z"},
                        "transit": {"utc": "2025-01-01T12:00:00Z"},
                        "set": {"utc": "2025-01-01T18:00:00Z"}}
            }
        }
    }

    with requests_mock.Mocker() as m:
        m.get(requests_mock.ANY, json=payload, status_code=200)
        data = utils.fetch_rise_set_times("sun", 1, 2)
        assert len(data) == 1
        evt = data[0]
        assert evt["rise"]["date"] == "2025-01-01T06:00:00Z"


@pytest.mark.django_db
def test_fetch_rise_set_times_404(settings):
    settings.RADIANT_DRIFT_API_KEY = "KEY"
    with requests_mock.Mocker() as m:
        m.get(requests_mock.ANY, status_code=404)
        assert utils.fetch_rise_set_times("sun", 1, 2) == []


@pytest.mark.django_db
def test_fetch_rise_set_times_invalid_body():
    assert utils.fetch_rise_set_times("mars", 1, 2) == []


# -------------------------------------------------------------------
# fetch_body_position
# -------------------------------------------------------------------

@pytest.mark.django_db
def test_fetch_body_position_success(settings):
    settings.RADIANT_DRIFT_API_KEY = "KEY"
    payload = {
        "response": {
            "2025-01-01T00:00:00Z": {"moon": {"azimuth": 123}}
        }
    }

    with requests_mock.Mocker() as m:
        m.get(requests_mock.ANY, json=payload, status_code=200)
        pos = utils.fetch_body_position("moon", "2025-01-01T00:00:00Z", 1, 2)
        assert pos["azimuth"] == 123


@pytest.mark.django_db
def test_fetch_body_position_error(settings):
    settings.RADIANT_DRIFT_API_KEY = "KEY"
    with requests_mock.Mocker() as m:
        m.get(requests_mock.ANY, status_code=500)
        pos = utils.fetch_body_position("moon", "2025-01-01T00:00:00Z", 1, 2)
        assert pos is None


def test_fetch_body_position_invalid_body():
    assert utils.fetch_body_position("jupiter", "x", 1, 2) is None


# -------------------------------------------------------------------
# fetch_moon_phase
# -------------------------------------------------------------------

def test_fetch_moon_phase(monkeypatch):
    monkeypatch.setattr(utils, "fetch_body_position", lambda *a, **k: {
        "illuminatedFraction": 0.5,
        "phase": "Waxing",
        "age": 7
    })
    mp = utils.fetch_moon_phase("2025-01-01", 1, 2)
    assert mp["phase"] == "Waxing"


def test_fetch_moon_phase_none(monkeypatch):
    monkeypatch.setattr(utils, "fetch_body_position", lambda *a, **k: None)
    assert utils.fetch_moon_phase("x", 1, 2) is None


# -------------------------------------------------------------------
# fetch_solar_eclipse_data
# -------------------------------------------------------------------

@pytest.mark.django_db
def test_fetch_solar_eclipse_data_success(settings):
    settings.RADIANT_DRIFT_API_KEY = "KEY"
    payload = {"events": [{"type": "total"}]}

    with requests_mock.Mocker() as m:
        m.get(requests_mock.ANY, json=payload, status_code=200)
        out = utils.fetch_solar_eclipse_data()
        assert out["events"][0]["type"] == "total"


@pytest.mark.django_db
def test_fetch_solar_eclipse_data_error(settings):
    settings.RADIANT_DRIFT_API_KEY = "KEY"
    with requests_mock.Mocker() as m:
        m.get(requests_mock.ANY, status_code=500)
        assert utils.fetch_solar_eclipse_data() == []


# -------------------------------------------------------------------
# fetch_twilight_events
# -------------------------------------------------------------------

def test_fetch_twilight_events_success():
    payload = {
        "daily": {
            "time": ["2025-01-01"],
            "sunrise": ["2025-01-01T06:00"],
            "sunset": ["2025-01-01T18:00"]
        }
    }
    with requests_mock.Mocker() as m:
        m.get(utils.OPEN_METEO_API_BASE, json=payload, status_code=200)
        events = utils.fetch_twilight_events(1, 2)
        assert len(events) == 2
        assert events[0]["type"] == "Sunrise"


def test_fetch_twilight_events_error(monkeypatch):
    def bad_get(*a, **k):
        raise requests.RequestException("fail")
    monkeypatch.setattr(requests, "get", bad_get)
    assert utils.fetch_twilight_events(1, 2) == []


# -------------------------------------------------------------------
# Solar System OpenData
# -------------------------------------------------------------------

def test_fetch_celestial_body_positions_success(settings):
    settings.SSOD_APP_ID = "TOKEN"
    payload = {"englishName": "Mars", "meanRadius": 3390, "moons": [{"moon": "Phobos"}]}

    with requests_mock.Mocker() as m:
        m.get(requests_mock.ANY, json=payload, status_code=200)
        pos = utils.fetch_celestial_body_positions()
        assert pos[0]["name"] == "Mars"
        assert pos[0]["meanRadius"] == 3390


def test_fetch_celestial_body_positions_error(settings):
    settings.SSOD_APP_ID = "TOKEN"
    with requests_mock.Mocker() as m:
        m.get(requests_mock.ANY, status_code=500)
        out = utils.fetch_celestial_body_positions()
        assert isinstance(out, list)


# -------------------------------------------------------------------
# Visibility Logic
# -------------------------------------------------------------------

@pytest.mark.django_db
def test_calculate_next_visibility_sun_success(monkeypatch):
    # Provide rise-set mock rows
    monkeypatch.setattr(utils, "fetch_rise_set_times", lambda *a, **k: [{
        "rise": {"date": "2999-01-01T06:00:00+00:00"}
    }])
    dt = utils.calculate_next_visibility("sun")
    assert isinstance(dt, datetime)


def test_calculate_next_visibility_invalid_body():
    assert utils.calculate_next_visibility("mars") is None