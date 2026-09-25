from datetime import datetime, timezone

# ConnectionRefusedError is imported from flask_socketio deliberately and
# shadows the Python builtin of the same name inside this module. python-socketio
# treats only *its* ConnectionRefusedError as a graceful refusal; the builtin is
# an OSError subclass with no relationship to it, so raising the builtin lets the
# exception escape the connect handler instead. Authentication holds either way,
# but the client then sees a generic failure rather than the reason, and the
# server logs a traceback on every unauthenticated attempt.
from flask_socketio import ConnectionRefusedError, emit

from auth import decode_token
from extensions import socketio
from models import Message, MessageRecipient, User, db

# sid -> {"user_id": int, "email": str}
connected_sids = {}
# user_id -> set of sids (a user can have multiple tabs open)
online_users = {}

HISTORY_LIMIT = 50


def _online_user_list():
    return [
        {"id": user_id, "email": User.query.get(user_id).email}
        for user_id in online_users
        if User.query.get(user_id) is not None
    ]


def _message_payload(message, ciphertext):
    return {
        "id": message.id,
        "from_user_id": message.from_user_id,
        "from_email": message.sender.email if message.sender else None,
        # Timestamps are written as UTC, but SQLite has no timezone type, so
        # SQLAlchemy hands back a naive datetime and isoformat() emits no
        # offset. JavaScript reads an offset-less ISO string as *local* time,
        # which made every message render hours adrift. Re-attaching UTC here
        # restores the offset so the client converts to local time correctly.
        "timestamp": message.timestamp.replace(tzinfo=timezone.utc).isoformat(),
        "nonce": message.nonce,
        "ciphertext": ciphertext,
    }


def _serialize_history(user_id):
    """The server can only hand back the ciphertext copy addressed to the
    requesting user — it has no way to decrypt it, and no other user's copy
    is any use to this client either.
    """
    rows = (
        db.session.query(MessageRecipient, Message)
        .join(Message, MessageRecipient.message_id == Message.id)
        .filter(MessageRecipient.user_id == user_id)
        .order_by(Message.timestamp.desc())
        .limit(HISTORY_LIMIT)
        .all()
    )
    return [_message_payload(message, mr.ciphertext) for mr, message in reversed(rows)]


@socketio.on("connect")
def handle_connect(auth):
    token = (auth or {}).get("token")
    payload = decode_token(token) if token else None

    if not payload:
        # Refusing the connection surfaces a `connect_error` client-side.
        raise ConnectionRefusedError("Authentication failed: invalid or missing token")

    from flask import request as flask_request

    sid = flask_request.sid
    user_id = payload["user_id"]
    email = payload["email"]

    connected_sids[sid] = {"user_id": user_id, "email": email}
    online_users.setdefault(user_id, set()).add(sid)

    emit("message_history", {"messages": _serialize_history(user_id)})

    emit(
        "user_joined",
        {
            "user": {"id": user_id, "email": email},
            "online_users": _online_user_list(),
        },
        broadcast=True,
    )


@socketio.on("disconnect")
def handle_disconnect():
    from flask import request as flask_request

    sid = flask_request.sid
    conn = connected_sids.pop(sid, None)
    if not conn:
        return

    user_id = conn["user_id"]
    sids = online_users.get(user_id)
    if sids:
        sids.discard(sid)
        if not sids:
            online_users.pop(user_id, None)

    if user_id not in online_users:
        emit(
            "user_left",
            {
                "user": {"id": user_id, "email": conn["email"]},
                "online_users": _online_user_list(),
            },
            broadcast=True,
        )


@socketio.on("send_message")
def handle_send_message(data):
    from flask import request as flask_request

    sid = flask_request.sid
    conn = connected_sids.get(sid)
    if not conn:
        emit("error", {"message": "Not authenticated"})
        return

    nonce = (data or {}).get("nonce")
    ciphertexts = (data or {}).get("ciphertexts")

    if not nonce or not isinstance(ciphertexts, dict) or not ciphertexts:
        emit("error", {"message": "Invalid message payload"})
        return

    try:
        message = Message(
            from_user_id=conn["user_id"],
            nonce=nonce,
            timestamp=datetime.now(timezone.utc),
        )
        db.session.add(message)
        db.session.flush()  # assigns message.id without committing yet

        for user_id_str, ciphertext in ciphertexts.items():
            db.session.add(
                MessageRecipient(
                    message_id=message.id,
                    user_id=int(user_id_str),
                    ciphertext=ciphertext,
                )
            )

        db.session.commit()
    except Exception:
        db.session.rollback()
        emit("error", {"message": "Failed to save message"})
        return

    # Personalized fan-out: every connected client gets only the ciphertext
    # copy that was encrypted for them, never anyone else's.
    for target_sid, target_conn in list(connected_sids.items()):
        target_ciphertext = ciphertexts.get(str(target_conn["user_id"]))
        if target_ciphertext is not None:
            emit("new_message", _message_payload(message, target_ciphertext), room=target_sid)


@socketio.on("get_message_history")
def handle_get_message_history():
    from flask import request as flask_request

    sid = flask_request.sid
    conn = connected_sids.get(sid)
    if not conn:
        return
    emit("message_history", {"messages": _serialize_history(conn["user_id"])})
