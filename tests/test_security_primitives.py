"""Unit tests for pure security helpers. These need no database or request context."""

import base64

import pytest

from app.security import totp
from app.security.csp import build_api_policy, build_frontend_policy
from app.security.production_checks import production_problems
from app.security.url_rules import image_url_problem, normalize_allowed_hosts

DEV_SECRET = "dev-only-change-me"


# ---------- TOTP (RFC 6238 test vectors, SHA-1, 8 digits) ----------

RFC_SECRET = base64.b32encode(b"12345678901234567890").decode()


@pytest.mark.parametrize(
    ("timestamp", "expected"),
    [
        (59, "94287082"),
        (1111111109, "07081804"),
        (1111111111, "14050471"),
        (1234567890, "89005924"),
        (2000000000, "69279037"),
    ],
)
def test_totp_matches_rfc_6238_vectors(timestamp, expected):
    assert totp.code_at(RFC_SECRET, timestamp // 30, digits=8) == expected


def test_totp_rejects_a_code_that_was_already_used():
    secret = totp.generate_secret()
    now = 1_000_000
    counter = totp.current_counter(now)
    code = totp.code_at(secret, counter)
    assert totp.verify_code(secret, code, now=now) == counter
    assert totp.verify_code(secret, code, last_used_step=counter, now=now) is None


def test_totp_accepts_one_step_of_drift_but_not_two():
    secret = totp.generate_secret()
    now = 1_000_000
    counter = totp.current_counter(now)
    assert totp.verify_code(secret, totp.code_at(secret, counter + 1), now=now) == counter + 1
    assert totp.verify_code(secret, totp.code_at(secret, counter + 2), now=now) is None


@pytest.mark.parametrize("bad", [None, "", "12345", "1234567", "12345a", 123456])
def test_totp_rejects_malformed_codes(bad):
    secret = totp.generate_secret()
    assert totp.verify_code(secret, bad, now=1_000_000) is None


def test_totp_provisioning_uri_contains_the_secret_and_issuer():
    uri = totp.provisioning_uri("ABCDEFGH", "admin@example.com")
    assert uri.startswith("otpauth://totp/TrayUP:admin@example.com?")
    assert "secret=ABCDEFGH" in uri and "issuer=TrayUP" in uri


# ---------- Image URL policy ----------

ALLOWED = ["images.unsplash.com"]


@pytest.mark.parametrize(
    "url",
    [
        "https://images.unsplash.com/photo-1.jpg?auto=format&fit=crop&w=900&q=82",
        "https://IMAGES.unsplash.com/photo-1.jpg",
        "https://images.unsplash.com:443/photo-1.jpg",
        "/static/menu/samosa.png",
    ],
)
def test_image_urls_on_approved_https_hosts_are_accepted(url):
    assert image_url_problem(url, ALLOWED) is None


@pytest.mark.parametrize(
    "url",
    [
        "http://images.unsplash.com/a.jpg",
        "https://evil.example.com/a.jpg",
        "https://images.unsplash.com.evil.com/a.jpg",
        "https://evil.com@images.unsplash.com/a.jpg",
        "https://user:pw@images.unsplash.com/a.jpg",
        "https://images.unsplash.com:8443/a.jpg",
        "javascript:alert(1)",
        "data:image/png;base64,AAAA",
        "//images.unsplash.com/a.jpg",
        'https://images.unsplash.com/a.jpg"onerror=1',
        "https://images.unsplash.com\\evil.com/a.jpg",
        "https:///a.jpg",
    ],
)
def test_unsafe_image_urls_are_rejected(url):
    assert image_url_problem(url, ALLOWED) is not None


def test_non_string_image_url_is_rejected():
    assert image_url_problem(None, ALLOWED) is not None
    assert image_url_problem(12, ALLOWED) is not None


def test_allowlist_is_normalized_and_validated():
    assert normalize_allowed_hosts([" Images.Unsplash.com ", "", "cdn.example.org"]) == frozenset(
        {"images.unsplash.com", "cdn.example.org"}
    )
    with pytest.raises(ValueError):
        normalize_allowed_hosts(["bad host;"])


# ---------- Content-Security-Policy ----------

def _directive(policy, name):
    for part in policy.split(";"):
        part = part.strip()
        if part.startswith(name + " ") or part == name:
            return part
    raise AssertionError(f"{name} missing from {policy!r}")


def test_frontend_policy_forbids_inline_script_and_eval():
    policy = build_frontend_policy(ALLOWED)
    script_src = _directive(policy, "script-src")
    assert "'unsafe-inline'" not in script_src
    assert "'unsafe-eval'" not in script_src
    assert "'self'" in script_src


def test_frontend_policy_limits_images_to_allowed_hosts():
    policy = build_frontend_policy(["images.unsplash.com", "cdn.example.org"])
    img_src = _directive(policy, "img-src")
    assert "https://images.unsplash.com" in img_src
    assert "https://cdn.example.org" in img_src
    assert "https:" not in img_src.replace("https://", "")


def test_frontend_policy_blocks_framing_and_plugins():
    policy = build_frontend_policy(ALLOWED)
    assert "frame-ancestors 'none'" in policy
    assert "object-src 'none'" in policy


def test_upgrade_insecure_requests_is_optional():
    assert "upgrade-insecure-requests" not in build_frontend_policy(ALLOWED)
    assert "upgrade-insecure-requests" in build_frontend_policy(ALLOWED, upgrade_insecure=True)


def test_api_policy_denies_everything_by_default():
    assert build_api_policy().startswith("default-src 'none'")


def test_policy_refuses_hosts_that_could_inject_directives():
    with pytest.raises(ValueError):
        build_frontend_policy(["evil.com; script-src *"])


# ---------- Production configuration ----------

def _good_production_config():
    return {
        "SECRET_KEY": "k" * 40,
        "RATELIMIT_STORAGE_URI": "rediss://cache.example:6379/0",
        "SESSION_COOKIE_SECURE": True,
        "DEBUG": False,
        "MENU_IMAGE_ALLOWED_HOSTS": ["images.unsplash.com"],
    }


def test_good_production_config_has_no_problems():
    assert production_problems(_good_production_config(), DEV_SECRET) == []


def test_production_refuses_in_memory_rate_limits():
    config = _good_production_config()
    config["RATELIMIT_STORAGE_URI"] = "memory://"
    problems = production_problems(config, DEV_SECRET)
    assert any("RATELIMIT_STORAGE_URI" in problem for problem in problems)


def test_production_refuses_the_development_secret_and_short_secrets():
    config = _good_production_config()
    config["SECRET_KEY"] = DEV_SECRET
    assert production_problems(config, DEV_SECRET)
    config["SECRET_KEY"] = "short"
    assert production_problems(config, DEV_SECRET)


def test_production_refuses_insecure_cookies_and_debug():
    config = _good_production_config()
    config["SESSION_COOKIE_SECURE"] = False
    config["DEBUG"] = True
    problems = production_problems(config, DEV_SECRET)
    assert len(problems) == 2
