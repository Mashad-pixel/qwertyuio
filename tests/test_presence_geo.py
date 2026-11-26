"""Pure presence logic: geofence maths, GPS sample rules and keyed hashing.

These tests need no database or Flask app and run in milliseconds.
"""
import math
import secrets

import pytest

from app.services.presence_geo import (
    EARTH_RADIUS_METERS,
    TOKEN_PATTERN,
    haversine_meters,
    keyed_digest,
    validate_location_sample,
)

# Test-only reference point. Not a real canteen location.
REF_LAT = 0.0
REF_LON = 0.0
NOW_MS = 1_800_000_000_000  # fixed "now" so the tests are deterministic


def _sample(**overrides):
    values = dict(
        latitude=REF_LAT,
        longitude=REF_LON,
        accuracy=12.0,
        timestamp_ms=NOW_MS - 2_000,
        now_ms=NOW_MS,
        max_accuracy_meters=75.0,
        max_age_seconds=60,
    )
    values.update(overrides)
    return validate_location_sample(**values)


# ---------- Haversine ----------

def test_haversine_same_point_is_zero():
    assert haversine_meters(12.9, 77.5, 12.9, 77.5) == pytest.approx(0.0, abs=1e-6)


def test_haversine_one_degree_of_latitude_is_about_111_km():
    distance = haversine_meters(0.0, 0.0, 1.0, 0.0)
    expected = math.radians(1.0) * EARTH_RADIUS_METERS
    assert distance == pytest.approx(expected, rel=1e-9)
    assert 111_000 < distance < 111_300


def test_haversine_is_symmetric():
    a = haversine_meters(12.9716, 77.5946, 12.9352, 77.6245)
    b = haversine_meters(12.9352, 77.6245, 12.9716, 77.5946)
    assert a == pytest.approx(b, rel=1e-12)


def test_haversine_antipodal_points_are_half_circumference():
    distance = haversine_meters(0.0, 0.0, 0.0, 180.0)
    assert distance == pytest.approx(math.pi * EARTH_RADIUS_METERS, rel=1e-9)


def test_haversine_100_metre_boundary_is_detected():
    # 0.0008983 degrees of latitude is about 99.9 m; 0.0009 is about 100.1 m.
    inside = haversine_meters(REF_LAT, REF_LON, REF_LAT + 0.0008983, REF_LON)
    outside = haversine_meters(REF_LAT, REF_LON, REF_LAT + 0.0009, REF_LON)
    assert inside < 100.0 < outside


# ---------- GPS sample validation ----------

def test_valid_sample_is_accepted():
    assert _sample() is None


def test_accuracy_exactly_at_limit_is_accepted():
    assert _sample(accuracy=75.0) is None


def test_accuracy_above_limit_is_rejected():
    code, message = _sample(accuracy=75.01)
    assert code == "LOCATION_ACCURACY_TOO_LOW"
    assert "GPS" in message


@pytest.mark.parametrize("accuracy", [0, -3.0, float("nan"), float("inf"), "12", None, True])
def test_malformed_accuracy_is_rejected(accuracy):
    code, _ = _sample(accuracy=accuracy)
    assert code == "LOCATION_INVALID"


@pytest.mark.parametrize("latitude, longitude", [
    (91.0, 0.0), (-90.5, 0.0), (0.0, 181.0), (0.0, -180.5),
    (float("nan"), 0.0), (0.0, float("inf")), ("12.9", 77.5), (True, 0.0), (None, 0.0),
])
def test_out_of_range_or_malformed_coordinates_are_rejected(latitude, longitude):
    code, _ = _sample(latitude=latitude, longitude=longitude)
    assert code == "LOCATION_INVALID"


def test_coordinates_at_the_poles_and_dateline_are_valid():
    assert _sample(latitude=90.0, longitude=180.0) is None
    assert _sample(latitude=-90.0, longitude=-180.0) is None


def test_stale_reading_is_rejected():
    code, message = _sample(timestamp_ms=NOW_MS - 61_000)
    assert code == "LOCATION_STALE"
    assert "too old" in message


def test_reading_just_inside_max_age_is_accepted():
    assert _sample(timestamp_ms=NOW_MS - 59_000) is None


def test_small_future_skew_is_tolerated_but_large_skew_is_rejected():
    assert _sample(timestamp_ms=NOW_MS + 10_000) is None
    code, _ = _sample(timestamp_ms=NOW_MS + 60_000)
    assert code == "LOCATION_INVALID"


@pytest.mark.parametrize("timestamp", [None, "1800000000000", float("nan"), True])
def test_malformed_timestamp_is_rejected(timestamp):
    code, _ = _sample(timestamp_ms=timestamp)
    assert code == "LOCATION_INVALID"


# ---------- Hashing and token format ----------

def test_keyed_digest_is_stable_and_hex():
    digest = keyed_digest("secret", "presence-token", "abc")
    assert digest == keyed_digest("secret", "presence-token", "abc")
    assert len(digest) == 64
    int(digest, 16)  # raises if not hex


def test_keyed_digest_separates_purposes_and_secrets():
    base = keyed_digest("secret", "presence-token", "value")
    assert base != keyed_digest("secret", "presence-session", "value")
    assert base != keyed_digest("other-secret", "presence-token", "value")
    assert base != keyed_digest("secret", "presence-token", "value2")


def test_generated_tokens_match_the_accepted_format():
    for _ in range(50):
        raw = secrets.token_urlsafe(32)
        assert TOKEN_PATTERN.match(raw)


@pytest.mark.parametrize("bad", ["", "short", "a" * 31, "a" * 129, "has space" + "a" * 40, "slash/" + "a" * 40, "dot." + "a" * 40])
def test_malformed_tokens_are_rejected_by_pattern(bad):
    assert TOKEN_PATTERN.match(bad) is None
