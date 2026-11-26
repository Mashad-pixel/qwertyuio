"""Fail-closed configuration rules for presence verification. No database needed."""
import pytest

from app.config import validate_runtime_settings


def _settings(**overrides):
    base = {
        "CANTEEN_LATITUDE": 12.9716,
        "CANTEEN_LONGITUDE": 77.5946,
        "PUBLIC_BASE_URL": "https://trayup.example",
        "PRESENCE_TOKEN_TTL_SECONDS": 10,
        "PRESENCE_SESSION_TTL_SECONDS": 180,
    }
    base.update(overrides)
    return base


def test_complete_production_configuration_is_accepted():
    validate_runtime_settings(_settings(), "production")


def test_production_refuses_to_start_without_canteen_coordinates():
    with pytest.raises(RuntimeError, match="CANTEEN_LATITUDE"):
        validate_runtime_settings(_settings(CANTEEN_LATITUDE=None, CANTEEN_LONGITUDE=None), "production")


def test_production_refuses_half_configured_coordinates():
    with pytest.raises(RuntimeError, match="Set both"):
        validate_runtime_settings(_settings(CANTEEN_LONGITUDE=None), "production")


def test_production_requires_https_public_base_url():
    with pytest.raises(RuntimeError, match="https"):
        validate_runtime_settings(_settings(PUBLIC_BASE_URL="http://trayup.example"), "production")
    with pytest.raises(RuntimeError, match="https"):
        validate_runtime_settings(_settings(PUBLIC_BASE_URL=""), "production")


def test_development_may_run_without_coordinates_because_ordering_fails_closed():
    validate_runtime_settings(_settings(CANTEEN_LATITUDE=None, CANTEEN_LONGITUDE=None), "development")


def test_out_of_range_coordinates_are_rejected_in_every_environment():
    with pytest.raises(RuntimeError, match="between -90"):
        validate_runtime_settings(_settings(CANTEEN_LATITUDE=95.0), "development")
    with pytest.raises(RuntimeError, match="between -90"):
        validate_runtime_settings(_settings(CANTEEN_LONGITUDE=-200.0), "testing")


def test_token_and_session_ttls_are_bounded():
    with pytest.raises(RuntimeError, match="TOKEN_TTL"):
        validate_runtime_settings(_settings(PRESENCE_TOKEN_TTL_SECONDS=60), "development")
    with pytest.raises(RuntimeError, match="SESSION_TTL"):
        validate_runtime_settings(_settings(PRESENCE_SESSION_TTL_SECONDS=10), "development")
