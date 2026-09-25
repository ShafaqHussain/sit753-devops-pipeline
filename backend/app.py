import os

from dotenv import load_dotenv

load_dotenv()

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from prometheus_flask_exporter import PrometheusMetrics
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import safe_join

from auth import generate_token, token_required
from extensions import socketio
from models import User, db


# Comma-separated list, e.g. "http://localhost:5173,http://localhost:5174" —
# supports running multiple frontend dev servers (different ports) against
# the same backend at once, since dev ports on this machine tend to shift
# when other projects claim the defaults.
#
# In the container the SPA is served from the same origin as the API, so the
# browser's Origin header is the container's own address rather than a Vite
# dev port. docker-compose therefore sets FRONTEND_ORIGIN=* — without it the
# Socket.IO handshake is rejected as cross-origin. Narrow this to the real
# hostname before any deployment that is not a marking demo.
FRONTEND_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("FRONTEND_ORIGIN", "http://localhost:5173").split(",")
    if origin.strip()
]

# Injected by the Docker build (see the APP_VERSION build arg) so a running
# container can report which release it is. The pipeline's Release stage tags
# the image and the Git commit with this same value, which is what makes a
# deployed container traceable back to a commit.
APP_VERSION = os.environ.get("APP_VERSION", "0.0.0-dev")

# Where the Dockerfile's first stage drops the compiled Vite bundle. Absolute
# so it resolves regardless of the working directory gunicorn starts in.
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


def create_app():
    # static_folder=None is deliberate. With a static folder set, Flask
    # registers its own "/<path:filename>" rule, which collides with the SPA
    # catch-all below; serving the bundle ourselves keeps one rule in charge.
    app = Flask(__name__, static_folder=None)
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
        "DATABASE_URL", "sqlite:///chat.db"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET_KEY", "dev-secret")
    app.config["JWT_SECRET_KEY"] = os.environ.get("JWT_SECRET_KEY", "dev-jwt-secret")

    CORS(app, resources={r"/*": {"origins": FRONTEND_ORIGINS}}, supports_credentials=True)

    db.init_app(app)

    with app.app_context():
        db.create_all()

    return app


app = create_app()

socketio.init_app(app, cors_allowed_origins=FRONTEND_ORIGINS)

# Exposes /metrics for Prometheus. Every route gets request counts, status
# code breakdowns and latency histograms without per-route instrumentation.
# Single-worker gunicorn (forced by Socket.IO) means no multiprocess
# collector is needed.
metrics = PrometheusMetrics(app)
metrics.info("app_info", "Encrypted chat backend", version=APP_VERSION)


@app.route("/health", methods=["GET"])
def health():
    """Liveness probe used by the Docker HEALTHCHECK, by docker-compose to
    order dependent services, and by the pipeline's post-deploy smoke test.
    Deliberately touches no database so it stays fast and cannot report a
    failure for an unrelated reason.
    """
    return jsonify({"status": "ok", "version": APP_VERSION}), 200


@app.route("/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    public_key = (data.get("public_key") or "").strip()

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400
    if not public_key:
        return jsonify({"error": "A public_key is required for end-to-end encryption"}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({"error": "An account with that email already exists"}), 409

    user = User(
        email=email,
        password_hash=generate_password_hash(password),
        public_key=public_key,
    )
    db.session.add(user)
    db.session.commit()

    token = generate_token(user)
    return jsonify({"token": token, "user": user.to_dict()}), 201


@app.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    user = User.query.filter_by(email=email).first()
    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({"error": "Invalid email or password"}), 401

    token = generate_token(user)
    return jsonify({"token": token, "user": user.to_dict()}), 200


@app.route("/users", methods=["GET"])
@token_required
def list_users():
    users = User.query.order_by(User.email.asc()).all()
    return jsonify({"users": [u.to_dict() for u in users]}), 200


@app.route("/users/me/public-key", methods=["PUT"])
@token_required
def update_public_key():
    """Lets a client register a freshly generated keypair when it has no
    local copy of its private key (new device, or cleared storage). Messages
    encrypted under the old public key become permanently undecryptable —
    that's an inherent, expected property of E2E encryption, not a bug.
    """
    data = request.get_json(silent=True) or {}
    public_key = (data.get("public_key") or "").strip()
    if not public_key:
        return jsonify({"error": "public_key is required"}), 400

    user = db.session.get(User, request.user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    user.public_key = public_key
    db.session.commit()
    return jsonify({"user": user.to_dict()}), 200


@app.errorhandler(404)
def not_found(_e):
    return jsonify({"error": "Not found"}), 404


@app.errorhandler(500)
def server_error(_e):
    return jsonify({"error": "Internal server error"}), 500


# --- SPA delivery -----------------------------------------------------------
# Registered last so the API rules above read as a group. Werkzeug matches
# static rules ahead of dynamic ones regardless of registration order, so
# "/login" and friends still win over this catch-all.


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_spa(path):
    """Serves the compiled React bundle, falling back to index.html so that
    client-side routes survive a page refresh.

    safe_join returns None for anything that would escape STATIC_DIR, which
    keeps a crafted path like "../../etc/passwd" from being served.
    """
    if path:
        candidate = safe_join(STATIC_DIR, path)
        if candidate and os.path.isfile(candidate):
            return send_from_directory(STATIC_DIR, path)

    index_path = os.path.join(STATIC_DIR, "index.html")
    if not os.path.isfile(index_path):
        # Running the backend alone during development, with the frontend on
        # the Vite dev server. Say so plainly instead of raising.
        return (
            jsonify(
                {
                    "error": "No frontend build found",
                    "detail": "Run `npm run build` in frontend/, or use the Vite dev server.",
                }
            ),
            404,
        )
    return send_from_directory(STATIC_DIR, "index.html")


# Registers Socket.IO event handlers (connect, disconnect, send_message, ...) on `socketio`.
import socketio_events  # noqa: E402,F401  (must be imported after `app`/`socketio` exist)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    socketio.run(
        app,
        host="0.0.0.0",
        port=port,
        # debug=False is deliberate: Flask-SocketIO's threading async_mode
        # calls Flask's own app.run() under the hood, which reloads based on
        # app.debug rather than honoring use_reloader=False passed here. A
        # debug=True + use_reloader=False combination silently spawns a
        # reloader child anyway, on a possibly different interpreter, which
        # then serves traffic while this process's logs look fine — a stale
        # environment loaded into that child is invisible until you go
        # looking for it.
        debug=False,
        allow_unsafe_werkzeug=True,
        use_reloader=False,
    )
