from app.extensions import db
from app.models.user import User

STUDENT_EMAIL = "student@test.com"
STUDENT_PASSWORD = "StrongPass123!"


def login(client, email=STUDENT_EMAIL, password=STUDENT_PASSWORD):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def test_login_success_starts_session(anon_client, student):
    response = login(anon_client)

    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True
    assert body["data"]["email"] == STUDENT_EMAIL
    assert "password_hash" not in body["data"]

    me = anon_client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.get_json()["data"]["role"] == "STUDENT"


def test_email_is_case_and_space_insensitive(anon_client, student):
    response = login(anon_client, email="  STUDENT@test.com ")

    assert response.status_code == 200


def test_wrong_password_is_rejected(anon_client, student):
    response = login(anon_client, password="wrong-password")

    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_unknown_email_gives_same_error_as_wrong_password(anon_client, student):
    response = login(anon_client, email="nobody@test.com")

    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_inactive_user_cannot_login(anon_client, app):
    user = User(name="Old Account", email="old@test.com", role="STUDENT", is_active=False)
    user.set_password(STUDENT_PASSWORD)
    db.session.add(user)
    db.session.commit()

    response = login(anon_client, email="old@test.com")

    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_missing_fields_are_rejected(anon_client, student):
    response = anon_client.post("/api/auth/login", json={"email": STUDENT_EMAIL})

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "MISSING_FIELDS"


def test_me_requires_login(anon_client):
    response = anon_client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "AUTH_REQUIRED"


def test_logout_ends_session(anon_client, student):
    login(anon_client)

    assert anon_client.post("/api/auth/logout").status_code == 200
    assert anon_client.get("/api/auth/me").status_code == 401


def test_real_login_can_create_order(anon_client, student, menu):
    login(anon_client)

    response = anon_client.post(
        "/api/orders",
        json={"items": [{"menu_item_id": menu["samosa"].id, "quantity": 2}]},
        headers={"Idempotency-Key": "real-login-test"},
    )

    assert response.status_code == 201
    assert response.get_json()["data"]["total_paise"] == 3000


def test_login_returns_csrf_token_for_next_requests(anon_client, student):
    response = anon_client.post(
        "/api/auth/login",
        json={"email": "student@test.com", "password": "StrongPass123!"},
    )

    assert response.status_code == 200
    token = response.get_json()["data"]["csrf_token"]
    assert isinstance(token, str) and len(token) > 20



def test_registration_creates_student_and_ignores_requested_role(anon_client):
    response = anon_client.post(
        "/api/auth/register",
        json={
            "name": "New Student",
            "email": "  NEW@student.test ",
            "password": "StrongPass123!",
            "role": "ADMIN",
        },
    )
    assert response.status_code == 201
    data = response.get_json()["data"]
    assert data["role"] == "STUDENT"
    assert data["email"] == "new@student.test"
    assert isinstance(data["csrf_token"], str)
    user = User.query.filter_by(email="new@student.test").one()
    assert user.role == "STUDENT"
    assert user.check_password("StrongPass123!")
    assert anon_client.get("/api/auth/me").get_json()["data"]["role"] == "STUDENT"


def test_registration_rejects_weak_password(anon_client):
    response = anon_client.post(
        "/api/auth/register",
        json={"name": "New Student", "email": "weak@test.com", "password": "password"},
    )
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "INVALID_REGISTRATION"
    assert User.query.filter_by(email="weak@test.com").count() == 0


def test_registration_rejects_duplicate_email_case_insensitively(anon_client, student):
    response = anon_client.post(
        "/api/auth/register",
        json={"name": "Duplicate", "email": " STUDENT@Test.com ", "password": "StrongPass123!"},
    )
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "EMAIL_UNAVAILABLE"
    assert User.query.filter_by(email=STUDENT_EMAIL).count() == 1
