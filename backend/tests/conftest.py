"""Shared test fixtures.

The application builds its Flask app at import time (`app = create_app()`),
so configuration has to be in the environment *before* app.py is imported.
python-dotenv does not override variables that are already set, so anything
put into os.environ here wins over backend/.env.
"""

import os
import sys
import tempfile

# Import the backend package from the directory above tests/, so the suite
# runs the same whether pytest is invoked from backend/ or from the repo root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_db_handle, _db_path = tempfile.mkstemp(suffix=".db", prefix="chat-test-")
os.close(_db_handle)

# Forward slashes keep the URL valid on Windows as well as Linux.
os.environ["DATABASE_URL"] = "sqlite:///" + _db_path.replace("\\", "/")
os.environ["JWT_SECRET_KEY"] = "test-jwt-secret"
os.environ["FLASK_SECRET_KEY"] = "test-flask-secret"
os.environ["FRONTEND_ORIGIN"] = "http://localhost:5173"
os.environ["SOCKETIO_ASYNC_MODE"] = "threading"

import pytest  # noqa: E402

from app import app as flask_app  # noqa: E402
from extensions import socketio as flask_socketio  # noqa: E402
from models import db  # noqa: E402

PUBLIC_KEY = "dGVzdC1wdWJsaWMta2V5LWJhc2U2NC1wbGFjZWhvbGRlcg=="


@pytest.fixture(autouse=True)
def clean_state():
    """Every test starts against empty tables and an empty presence registry,
    so test ordering cannot matter and one failure cannot cascade into the
    next test through module-level socket state.
    """
    import socketio_events

    socketio_events.connected_sids.clear()
    socketio_events.online_users.clear()

    with flask_app.app_context():
        db.drop_all()
        db.create_all()

    yield

    socketio_events.connected_sids.clear()
    socketio_events.online_users.clear()
    with flask_app.app_context():
        db.session.remove()


@pytest.fixture()
def app():
    return flask_app


@pytest.fixture()
def socketio():
    return flask_socketio


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def make_user(client):
    """Registers a user and returns its id, email and a valid JWT."""

    def _make(email="alice@example.com", password="Str0ng-Passw0rd"):
        res = client.post(
            "/register",
            json={"email": email, "password": password, "public_key": PUBLIC_KEY},
        )
        body = res.get_json()
        return {
            "id": body["user"]["id"],
            "email": body["user"]["email"],
            "password": password,
            "token": body["token"],
        }

    return _make


@pytest.fixture()
def user(make_user):
    return make_user()


@pytest.fixture()
def auth_headers(user):
    return {"Authorization": "Bearer " + user["token"]}
