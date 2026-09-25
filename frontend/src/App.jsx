import { useState } from "react";

import AuthPage from "./pages/AuthPage.jsx";
import ChatPage from "./pages/ChatPage.jsx";

function loadStoredAuth() {
  const token = localStorage.getItem("token");
  const userRaw = localStorage.getItem("user");
  if (!token || !userRaw) return null;
  try {
    return { token, user: JSON.parse(userRaw) };
  } catch {
    return null;
  }
}

export default function App() {
  const [auth, setAuth] = useState(loadStoredAuth);

  function handleAuthenticated(token, user) {
    localStorage.setItem("token", token);
    localStorage.setItem("user", JSON.stringify(user));
    setAuth({ token, user });
  }

  function handleLogout() {
    localStorage.removeItem("token");
    localStorage.removeItem("user");
    setAuth(null);
  }

  if (!auth) {
    return <AuthPage onAuthenticated={handleAuthenticated} />;
  }

  return <ChatPage token={auth.token} user={auth.user} onLogout={handleLogout} />;
}
