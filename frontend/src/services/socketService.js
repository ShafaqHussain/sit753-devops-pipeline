import { io } from "socket.io-client";

// undefined (not "") is what makes socket.io-client fall back to the origin
// that served the page, which is what the container needs: an empty string is
// parsed as a URL and fails. frontend/.env points this at the backend during
// development, when Vite serves the page from a different port.
const SOCKET_URL = import.meta.env.VITE_SOCKET_URL || undefined;

let socket = null;

export function connectSocket(token) {
  if (socket) {
    socket.disconnect();
  }

  socket = io(SOCKET_URL, {
    auth: { token },
    autoConnect: true,
    reconnection: true,
  });

  return socket;
}

export function getSocket() {
  return socket;
}

export function disconnectSocket() {
  if (socket) {
    socket.disconnect();
    socket = null;
  }
}
