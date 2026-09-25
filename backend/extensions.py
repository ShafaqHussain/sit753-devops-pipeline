"""Shared extension instances.

Kept in their own module (rather than defined in app.py) so that other
modules can import `socketio`/`db` without triggering app.py to be imported
a second time under a different module name when it's run directly via
`python app.py`.
"""

import os

from flask_socketio import SocketIO

# "threading" suits the local dev server started by `python app.py`.
# The container runs gunicorn with an eventlet worker, which needs
# async_mode="eventlet" or the handshake silently degrades to long-polling
# and WebSocket upgrades never complete. docker-compose sets
# SOCKETIO_ASYNC_MODE=eventlet so the same source serves both.
socketio = SocketIO(async_mode=os.environ.get("SOCKETIO_ASYNC_MODE", "threading"))
