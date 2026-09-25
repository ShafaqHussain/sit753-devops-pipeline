"""REST endpoint tests: health, registration, login and the user directory."""

import jwt
import pytest

# Declared here rather than imported from conftest because parametrize needs
# it at collection time, before fixtures exist.
PUBLIC_KEY = "dGVzdC1wdWJsaWMta2V5LWJhc2U2NC1wbGFjZWhvbGRlcg=="


# --- health -----------------------------------------------------------------


def test_health_reports_ok_and_version(client):
    res = client.get("/health")
    assert res.status_code == 200
    body = res.get_json()
    assert body["status"] == "ok"
    assert body["version"]


# --- registration -----------------------------------------------------------


def test_register_returns_token_and_user(client):
    res = client.post(
        "/register",
        json={
            "email": "new@example.com",
            "password": "Str0ng-Passw0rd",
            "public_key": PUBLIC_KEY,
        },
    )
    assert res.status_code == 201
    body = res.get_json()
    assert body["token"]
    assert body["user"]["email"] == "new@example.com"
    assert body["user"]["public_key"] == PUBLIC_KEY


def test_register_normalises_email_case(client):
    client.post(
        "/register",
        json={
            "email": "  MixedCase@Example.COM  ",
            "password": "Str0ng-Passw0rd",
            "public_key": PUBLIC_KEY,
        },
    )
    res = client.post(
        "/login",
        json={"email": "mixedcase@example.com", "password": "Str0ng-Passw0rd"},
    )
    assert res.status_code == 200


@pytest.mark.parametrize(
    "payload,expected",
    [
        ({"password": "Str0ng-Passw0rd", "public_key": PUBLIC_KEY}, 400),
        ({"email": "a@b.com", "public_key": PUBLIC_KEY}, 400),
        ({"email": "a@b.com", "password": "short", "public_key": PUBLIC_KEY}, 400),
        ({"email": "a@b.com", "password": "Str0ng-Passw0rd"}, 400),
    ],
)
def test_register_rejects_incomplete_payloads(client, payload, expected):
    assert client.post("/register", json=payload).status_code == expected


def test_register_rejects_duplicate_email(client, user):
    res = client.post(
        "/register",
        json={
            "email": user["email"],
            "password": "Another-Passw0rd",
            "public_key": PUBLIC_KEY,
        },
    )
    assert res.status_code == 409


def test_password_is_hashed_not_stored_in_plaintext(app, client, user):
    from models import User

    with app.app_context():
        stored = User.query.filter_by(email=user["email"]).first()
        assert user["password"] not in stored.password_hash
        # Werkzeug encodes the algorithm as the first colon-delimited field.
        # Werkzeug 3 defaults to scrypt; accept pbkdf2 so the assertion does
        # not break on a platform without scrypt support in OpenSSL.
        assert stored.password_hash.split(":")[0] in {"scrypt", "pbkdf2"}


# --- login ------------------------------------------------------------------


def test_login_returns_a_decodable_token(app, client, user):
    res = client.post(
        "/login", json={"email": user["email"], "password": user["password"]}
    )
    assert res.status_code == 200

    token = res.get_json()["token"]
    payload = jwt.decode(
        token, app.config["JWT_SECRET_KEY"], algorithms=["HS256"]
    )
    assert payload["user_id"] == user["id"]
    assert payload["email"] == user["email"]
    assert payload["exp"] > payload["iat"]


def test_login_rejects_wrong_password(client, user):
    res = client.post(
        "/login", json={"email": user["email"], "password": "definitely-wrong"}
    )
    assert res.status_code == 401


def test_login_rejects_unknown_email(client):
    res = client.post(
        "/login", json={"email": "nobody@example.com", "password": "Str0ng-Passw0rd"}
    )
    assert res.status_code == 401


# --- authorisation ----------------------------------------------------------


def test_user_directory_requires_a_token(client):
    assert client.get("/users").status_code == 401


def test_user_directory_rejects_a_malformed_token(client):
    res = client.get("/users", headers={"Authorization": "Bearer not-a-real-jwt"})
    assert res.status_code == 401


def test_user_directory_rejects_a_token_signed_with_another_key(client, user):
    import datetime

    forged = jwt.encode(
        {
            "user_id": user["id"],
            "email": user["email"],
            "exp": datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(days=1),
        },
        "an-attackers-secret",
        algorithm="HS256",
    )
    res = client.get("/users", headers={"Authorization": "Bearer " + forged})
    assert res.status_code == 401


def test_user_directory_lists_public_keys_but_no_hashes(client, auth_headers, make_user):
    make_user(email="bob@example.com")

    res = client.get("/users", headers=auth_headers)
    assert res.status_code == 200

    users = res.get_json()["users"]
    assert len(users) == 2
    for entry in users:
        assert entry["public_key"]
        assert "password_hash" not in entry
        assert "password" not in entry


# --- public key rotation ----------------------------------------------------


def test_public_key_can_be_rotated(client, auth_headers):
    rotated = "cm90YXRlZC1wdWJsaWMta2V5LXBsYWNlaG9sZGVyLXZhbHVl"
    res = client.put(
        "/users/me/public-key", headers=auth_headers, json={"public_key": rotated}
    )
    assert res.status_code == 200
    assert res.get_json()["user"]["public_key"] == rotated


def test_public_key_rotation_rejects_an_empty_key(client, auth_headers):
    res = client.put(
        "/users/me/public-key", headers=auth_headers, json={"public_key": "   "}
    )
    assert res.status_code == 400


def test_public_key_rotation_requires_a_token(client):
    res = client.put("/users/me/public-key", json={"public_key": PUBLIC_KEY})
    assert res.status_code == 401
