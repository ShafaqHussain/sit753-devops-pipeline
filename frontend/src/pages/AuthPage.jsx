import { useState } from "react";

import { login, register } from "../services/api.js";
import { generateKeyPair, savePrivateKey } from "../services/cryptoService.js";

export default function AuthPage({ onAuthenticated }) {
  const [mode, setMode] = useState("login"); // "login" | "register"
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      let data;
      if (mode === "login") {
        data = await login(email, password);
      } else {
        // Generate this account's E2E keypair client-side; the private key
        // never leaves the browser.
        const keyPair = await generateKeyPair();
        data = await register(email, password, keyPair.publicKey);
        savePrivateKey(data.user.id, keyPair.privateKey);
      }
      onAuthenticated(data.token, data.user);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="auth-page">
      <form className="auth-card" onSubmit={handleSubmit}>
        <h1>{mode === "login" ? "Welcome back" : "Create an account"}</h1>
        <p className="auth-subtitle">
          {mode === "login" ? "Log in to start chatting" : "Sign up to join the chat"}
        </p>

        <label className="field">
          <span>Email</span>
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
            autoComplete="email"
          />
        </label>

        <label className="field">
          <span>Password</span>
          <input
            type="password"
            required
            minLength={6}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="At least 6 characters"
            autoComplete={mode === "login" ? "current-password" : "new-password"}
          />
        </label>

        {error && <div className="auth-error">{error}</div>}

        <button type="submit" className="btn-primary" disabled={loading}>
          {loading ? "Please wait…" : mode === "login" ? "Log In" : "Register"}
        </button>

        <button
          type="button"
          className="btn-link"
          onClick={() => {
            setMode(mode === "login" ? "register" : "login");
            setError("");
          }}
        >
          {mode === "login"
            ? "Need an account? Register"
            : "Already have an account? Log in"}
        </button>
      </form>
    </div>
  );
}
