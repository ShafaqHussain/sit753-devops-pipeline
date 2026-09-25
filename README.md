# Real-Time Chat Application — Phase 2 (End-to-End Encrypted)

A full-stack real-time chat app: React (Vite) frontend + Flask/Socket.IO backend.
Messages are encrypted client-side with libsodium.js before they ever leave the
browser — the server only ever stores and relays ciphertext. It cannot read
message content.

## Stack

- **Frontend:** React 18 (Vite) + socket.io-client + libsodium-wrappers
- **Backend:** Flask, Flask-SocketIO, Flask-SQLAlchemy, PyJWT, python-dotenv
- **Database:** SQLite (dev) — swap `DATABASE_URL` for Postgres later
- **Auth:** JWT (7-day expiry), passwords hashed with Werkzeug
- **Encryption:** libsodium `crypto_box` (X25519 + XSalsa20-Poly1305), per-recipient

## Project structure

```
project-root/
├── backend/
│   ├── app.py                # Flask app, REST routes, Socket.IO init
│   ├── models.py              # SQLAlchemy models (User, Message, MessageRecipient)
│   ├── socketio_events.py     # Socket.IO event handlers
│   ├── auth.py                # JWT encode/decode + auth decorator
│   ├── extensions.py          # shared `socketio` instance (see Troubleshooting)
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── pages/AuthPage.jsx
│   │   ├── pages/ChatPage.jsx
│   │   ├── components/MessageList.jsx
│   │   ├── components/MessageInput.jsx
│   │   ├── components/UserSidebar.jsx
│   │   ├── services/api.js
│   │   ├── services/socketService.js
│   │   ├── services/cryptoService.js   # libsodium keypair gen + encrypt/decrypt
│   │   ├── App.jsx
│   │   └── index.css
│   ├── .env.example
│   └── package.json
└── README.md
```

## Backend setup

```bash
cd backend
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux
pip install -r requirements.txt
copy .env.example .env       # Windows (cp .env.example .env on macOS/Linux)
```

Edit `.env` and set real random values for `FLASK_SECRET_KEY` and `JWT_SECRET_KEY`
(e.g. `python -c "import secrets; print(secrets.token_hex(32))"`).

Run the server:

```bash
python app.py
```

The API + Socket.IO server starts on `http://localhost:5000`. The SQLite database
and tables are created automatically on first run, at `backend/instance/chat.db`.

## Frontend setup

```bash
cd frontend
npm install
copy .env.example .env        # Windows (cp .env.example .env on macOS/Linux)
npm run dev
```

The app runs on `http://localhost:5173` (Vite default) and talks to the backend
at the URL in `frontend/.env` (`VITE_API_URL`, `VITE_SOCKET_URL`).

## How the encryption works

Each account has an X25519 keypair (libsodium `crypto_box_keypair`), generated
**client-side at registration**:

1. The browser generates a keypair. The public key is sent to `/register` and
   stored on the user record; the private key is written only to that
   browser's `localStorage` (keyed by user id) and never sent anywhere.
2. To send a message, the sender's client fetches the current public-key
   directory (`GET /users`) and encrypts the plaintext **separately for every
   registered user**, including itself (so it can display its own sent
   messages), using `crypto_box_easy(plaintext, nonce, recipientPublicKey,
   senderPrivateKey)`. One random nonce is generated per message and reused
   across recipients — that's safe because `crypto_box` derives a distinct
   shared key per (sender, recipient) pair, so the (nonce, shared-key) pair
   stays unique.
3. The client emits `{ nonce, ciphertexts: { [userId]: ciphertext } }` over
   Socket.IO. The server stores one `Message` row (sender + nonce + timestamp)
   and one `MessageRecipient` row per ciphertext — it never sees plaintext.
4. On broadcast, each connected client is sent **only its own ciphertext**
   entry (personalized `emit(..., room=sid)`), never anyone else's. History
   requests are filtered the same way.
5. Each recipient decrypts with `crypto_box_open_easy(ciphertext, nonce,
   senderPublicKey, myPrivateKey)`.

### Known limitations (by design, for this phase)

- **The private key lives only in that browser's `localStorage`.** Logging
  into the same account from a different browser/device — or clearing site
  data — means that browser has no way to decrypt anything. The app detects
  this and shows a **"Generate New Key"** recovery flow, but regenerating
  uploads a *new* public key and permanently orphans anything encrypted under
  the old one. This is expected E2E behavior (comparable to a Signal "safety
  number changed" reset), not a bug.
- **A user who registers after a message was sent can never decrypt it** —
  they weren't in the recipient fan-out at send time, so no ciphertext copy
  exists for them. History is naturally scoped to "since you had keys."
- **Other clients may briefly hold a stale public key** for someone who just
  regenerated theirs, since key-directory refreshes happen on fetch/`user_joined`
  rather than a dedicated key-rotation push. Refreshing the page picks up the
  latest key.
- Encryption is per-recipient fan-out to everyone currently registered (a
  small/medium team room), not a scalable group-key scheme — fine for this
  phase, not what you'd want for a huge room.

## Trying it out

1. Start the backend (`python app.py`) and the frontend (`npm run dev`).
2. Open `http://localhost:5173` in two browser tabs (or one normal + one private
   window, so `localStorage` doesn't collide).
3. **Register** (not just log in) a different user in each tab — registration
   is what generates and stores that browser's keypair.
4. Send messages — they should appear in both tabs in real time, decrypted,
   with sender name and timestamp.
5. Refresh a tab — history reloads and re-decrypts from the database.
6. Close a tab — the other tab should see that user go offline in the sidebar.
7. To see the encryption actually working: open `backend/instance/chat.db`
   with a SQLite browser (or `sqlite3` CLI) and look at the `message_recipients`
   table — `ciphertext` should be unreadable base64, not your message text.

## REST API

| Method | Path                    | Auth        | Description                                          |
|--------|-------------------------|-------------|-------------------------------------------------------|
| POST   | `/register`             | none        | Create a user with `{email, password, public_key}`     |
| POST   | `/login`                | none        | Returns `{token, user}`                                |
| GET    | `/users`                | Bearer JWT  | List all users, including each one's `public_key`       |
| PUT    | `/users/me/public-key`  | Bearer JWT  | Replace your stored public key (key-recovery flow)      |

## Socket.IO events

Client connects with `io(url, { auth: { token } })`.

**Client → Server**
- `send_message` `{ nonce, ciphertexts: { [userId]: ciphertext } }` — one encrypted copy per recipient
- `get_message_history` — re-request your own decryptable history

**Server → Client**
- `message_history` `{ messages: [{ id, from_user_id, from_email, timestamp, nonce, ciphertext }] }` — your ciphertext copies only, sent on connect and on request
- `new_message` `{ id, from_user_id, from_email, timestamp, nonce, ciphertext }` — personalized per recipient, not a raw broadcast
- `user_joined` `{ user, online_users }` — broadcast when a user connects
- `user_left` `{ user, online_users }` — broadcast when a user's last tab disconnects
- `error` `{ message }` — validation/server errors
- `connect_error` — emitted client-side if the JWT is missing/invalid (server refuses the connection)

## Notes on this implementation

- Timestamps are always set server-side (`datetime.now(timezone.utc)`), never
  trusted from the client.
- A user can have multiple tabs open; they're only marked offline once every
  connection for that user closes.
- "Offline delivery" means: ciphertext is persisted to SQLite regardless of
  who's online, and any client reconnecting receives its `message_history` via
  the same personalized fan-out.

## Troubleshooting

- **`python -m venv` fails to launch / corrupt install**: if your default `python`
  is broken, list other installs with `py -0p` (Windows) and target one
  explicitly, e.g. `py -3.11 -m venv venv`.
- **Messages don't broadcast / nothing happens after `send_message`**: make
  sure `socketio_events.py` and `app.py` both import `socketio` from
  `extensions.py`, not from each other. Importing `socketio` via `from app
  import socketio` while running `python app.py` directly causes Python to
  load `app.py` a *second* time under a different module name, producing a
  second `SocketIO` instance that the event handlers silently attach to
  instead of the one actually serving requests — connections succeed but no
  events ever fire.
- **Browser autofill submitting saved credentials into the register/login
  form** during automated testing: disable autocomplete on those fields
  (`autoComplete="off"`) if you're scripting the UI, or test with a private
  window per user.
- **"Unable to decrypt this message" on everything**: usually means
  `localStorage` doesn't have this browser's private key for the logged-in
  account (wrong browser/profile, or storage was cleared) — use "Generate New
  Key" on the chat page, understanding it orphans old history.
- **Upgrading from the Phase 1 database**: the schema changed (`User.public_key`
  is required; `Message`/`MessageRecipient` replaced the old single-table
  design). Delete `backend/instance/chat.db` and let it recreate — existing
  Phase 1 accounts and messages aren't compatible with Phase 2.

## Next: Phase 3?

Not currently scoped. Natural next steps if you want to keep going: file/image
attachments, group channels instead of one global room, message edit/delete,
read receipts, or moving from SQLite to Postgres for a real deployment.
