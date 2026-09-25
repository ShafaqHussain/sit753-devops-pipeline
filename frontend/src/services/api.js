// Empty string means "same origin", which is how the container serves this:
// Flask hosts both the API and the compiled bundle. During development
// frontend/.env sets VITE_API_URL to the Vite dev server's backend.
const API_URL = import.meta.env.VITE_API_URL ?? "";

async function request(path, options = {}) {
  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });

  const data = await res.json().catch(() => ({}));

  if (!res.ok) {
    throw new Error(data.error || `Request failed with status ${res.status}`);
  }

  return data;
}

export function register(email, password, publicKey) {
  return request("/register", {
    method: "POST",
    body: JSON.stringify({ email, password, public_key: publicKey }),
  });
}

export function login(email, password) {
  return request("/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export function getUsers(token) {
  return request("/users", {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function updatePublicKey(token, publicKey) {
  return request("/users/me/public-key", {
    method: "PUT",
    headers: { Authorization: `Bearer ${token}` },
    body: JSON.stringify({ public_key: publicKey }),
  });
}
