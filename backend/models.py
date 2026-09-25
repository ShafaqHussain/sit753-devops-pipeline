from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def utcnow():
    return datetime.now(timezone.utc)


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    # Base64-encoded X25519 public key (libsodium crypto_box). The matching
    # private key never leaves the client.
    public_key = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "email": self.email,
            "public_key": self.public_key,
            "created_at": self.created_at.isoformat(),
        }


class Message(db.Model):
    """A message envelope. The actual ciphertext is per-recipient (see
    MessageRecipient) since each copy is encrypted separately with that
    recipient's public key. The nonce is safe to reuse across recipients of
    the same message because crypto_box derives a distinct shared key per
    (sender, recipient) pair.
    """

    __tablename__ = "messages"

    id = db.Column(db.Integer, primary_key=True)
    from_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    nonce = db.Column(db.String(64), nullable=False)
    timestamp = db.Column(db.DateTime, default=utcnow, nullable=False)

    sender = db.relationship("User", foreign_keys=[from_user_id])


class MessageRecipient(db.Model):
    """One encrypted copy of a Message, addressed to a single recipient."""

    __tablename__ = "message_recipients"

    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(
        db.Integer, db.ForeignKey("messages.id"), nullable=False, index=True
    )
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    ciphertext = db.Column(db.Text, nullable=False)

    message = db.relationship("Message", backref=db.backref("recipients", lazy="select"))
