import os
from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt
from flask import current_app, jsonify, request

from models import User

JWT_ALGORITHM = "HS256"


def generate_token(user: User) -> str:
    exp_days = int(os.environ.get("JWT_EXP_DAYS", 7))
    payload = {
        "user_id": user.id,
        "email": user.email,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(days=exp_days),
    }
    secret = current_app.config["JWT_SECRET_KEY"]
    return jwt.encode(payload, secret, algorithm=JWT_ALGORITHM)


def decode_token(token: str):
    """Returns the decoded payload, or None if the token is invalid/expired."""
    secret = current_app.config["JWT_SECRET_KEY"]
    try:
        return jwt.decode(token, secret, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None


def get_token_from_request():
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header.split(" ", 1)[1]
    return None


def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = get_token_from_request()
        if not token:
            return jsonify({"error": "Missing authentication token"}), 401

        payload = decode_token(token)
        if not payload:
            return jsonify({"error": "Invalid or expired token"}), 401

        request.user_id = payload["user_id"]
        request.user_email = payload["email"]
        return f(*args, **kwargs)

    return decorated
