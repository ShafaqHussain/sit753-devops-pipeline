"""Socket.IO integration tests.

These exercise the real event handlers through Flask-SocketIO's test client,
including the handshake, so they cover the authentication path that the REST
tests cannot reach.
"""

NONCE = "bm9uY2UtcGxhY2Vob2xkZXItMjQtYnl0ZXM="
CIPHERTEXT = "Y2lwaGVydGV4dC1wbGFjZWhvbGRlci1vcGFxdWUtdG8tc2VydmVy"


def _events(received, name):
    return [event for event in received if event["name"] == name]


# --- handshake --------------------------------------------------------------


def test_connection_succeeds_with_a_valid_token(app, socketio, user):
    sio = socketio.test_client(app, auth={"token": user["token"]})
    assert sio.is_connected()
    sio.disconnect()


def test_connection_is_refused_without_a_token(app, socketio):
    sio = socketio.test_client(app, auth={})
    assert not sio.is_connected()


def test_connection_is_refused_with_an_invalid_token(app, socketio):
    sio = socketio.test_client(app, auth={"token": "not-a-real-jwt"})
    assert not sio.is_connected()


def test_connect_delivers_message_history(app, socketio, user):
    sio = socketio.test_client(app, auth={"token": user["token"]})
    history = _events(sio.get_received(), "message_history")
    assert history
    assert history[0]["args"][0]["messages"] == []
    sio.disconnect()


# --- message relay ----------------------------------------------------------


def test_message_is_relayed_to_its_recipient(app, socketio, user):
    sio = socketio.test_client(app, auth={"token": user["token"]})
    sio.get_received()  # drain the connect events

    sio.emit(
        "send_message",
        {"nonce": NONCE, "ciphertexts": {str(user["id"]): CIPHERTEXT}},
    )

    delivered = _events(sio.get_received(), "new_message")
    assert delivered
    payload = delivered[0]["args"][0]
    assert payload["ciphertext"] == CIPHERTEXT
    assert payload["nonce"] == NONCE
    assert payload["from_user_id"] == user["id"]
    sio.disconnect()


def test_server_stores_only_ciphertext(app, socketio, user):
    """The project's headline claim is that the server cannot read messages.
    This asserts it: what lands in the database is byte-for-byte what the
    client encrypted, and the plaintext never appears anywhere in the row.
    """
    from models import Message, MessageRecipient

    sio = socketio.test_client(app, auth={"token": user["token"]})
    sio.get_received()

    sio.emit(
        "send_message",
        {"nonce": NONCE, "ciphertexts": {str(user["id"]): CIPHERTEXT}},
    )
    sio.get_received()

    with app.app_context():
        stored = MessageRecipient.query.one()
        assert stored.ciphertext == CIPHERTEXT

        envelope = Message.query.one()
        assert envelope.nonce == NONCE
        # The envelope carries routing data only: no plaintext column exists.
        assert not hasattr(envelope, "body")
        assert not hasattr(envelope, "plaintext")

    sio.disconnect()


def test_each_recipient_receives_only_their_own_copy(app, socketio, user, make_user):
    """Fan-out must be personalised. Bob must never be handed the ciphertext
    that was encrypted for Alice, since it would be useless to him and would
    leak the size and shape of someone else's message.
    """
    bob = make_user(email="bob@example.com")

    alice_sio = socketio.test_client(app, auth={"token": user["token"]})
    bob_sio = socketio.test_client(app, auth={"token": bob["token"]})
    alice_sio.get_received()
    bob_sio.get_received()

    alice_copy = "Y29weS1mb3ItYWxpY2U="
    bob_copy = "Y29weS1mb3ItYm9i"

    alice_sio.emit(
        "send_message",
        {
            "nonce": NONCE,
            "ciphertexts": {str(user["id"]): alice_copy, str(bob["id"]): bob_copy},
        },
    )

    alice_received = _events(alice_sio.get_received(), "new_message")
    bob_received = _events(bob_sio.get_received(), "new_message")

    assert alice_received[0]["args"][0]["ciphertext"] == alice_copy
    assert bob_received[0]["args"][0]["ciphertext"] == bob_copy

    alice_sio.disconnect()
    bob_sio.disconnect()


# --- payload validation -----------------------------------------------------


def test_message_without_a_nonce_is_rejected(app, socketio, user):
    sio = socketio.test_client(app, auth={"token": user["token"]})
    sio.get_received()

    sio.emit("send_message", {"ciphertexts": {str(user["id"]): CIPHERTEXT}})

    assert _events(sio.get_received(), "error")
    sio.disconnect()


def test_message_without_ciphertexts_is_rejected(app, socketio, user):
    sio = socketio.test_client(app, auth={"token": user["token"]})
    sio.get_received()

    sio.emit("send_message", {"nonce": NONCE, "ciphertexts": {}})

    assert _events(sio.get_received(), "error")
    sio.disconnect()


# --- history ----------------------------------------------------------------


def test_history_is_replayed_on_request(app, socketio, user):
    sio = socketio.test_client(app, auth={"token": user["token"]})
    sio.get_received()

    sio.emit(
        "send_message",
        {"nonce": NONCE, "ciphertexts": {str(user["id"]): CIPHERTEXT}},
    )
    sio.get_received()

    sio.emit("get_message_history")
    history = _events(sio.get_received(), "message_history")

    assert history
    messages = history[0]["args"][0]["messages"]
    assert len(messages) == 1
    assert messages[0]["ciphertext"] == CIPHERTEXT
    sio.disconnect()


def test_disconnect_removes_the_user_from_the_online_list(app, socketio, user):
    import socketio_events

    sio = socketio.test_client(app, auth={"token": user["token"]})
    assert user["id"] in socketio_events.online_users

    sio.disconnect()
    assert user["id"] not in socketio_events.online_users
