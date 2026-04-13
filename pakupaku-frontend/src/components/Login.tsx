import { useState } from "react";
import "./Login.css";

interface LoginProps {
  onLoginSuccess: () => void;
}

export default function Login({ onLoginSuccess }: LoginProps) {
  const [mode, setMode]               = useState<"login" | "register">("login");
  const [email, setEmail]             = useState("");
  const [username, setUsername]       = useState("");
  const [password, setPassword]       = useState("");
  const [error, setError]   = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const endpoint = mode === "login" ? "/auth/login" : "/auth/register";
      const body =
        mode === "login"
          ? { email, password }
          : { email, username, password };

      const res = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      if (!res.ok) {
        const errorData = await res.json();
        if (Array.isArray(errorData.detail)) {
          setError(errorData.detail[0].msg || "Validation error");
        } else if (typeof errorData.detail === "string") {
          setError(errorData.detail);
        } else {
          setError("Authentication failed");
        }
        return;
      }

      const data = await res.json();
      localStorage.setItem("token", data.access_token);
      onLoginSuccess();
    } catch (err) {
      console.error("Auth error:", err);
      setError("Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-root">
      <div className="login-card">
        <h1 className="login-title">Welcome to PakuPaku 🐕</h1>
        <p className="login-subtitle">Inclusive nutrition tracking</p>

        <form onSubmit={handleSubmit} className="login-form">
          <div className="tab-buttons">
            <button type="button" className={`tab-btn ${mode === "login" ? "active" : ""}`}
              onClick={() => setMode("login")} disabled={loading}>
              Login
            </button>
            <button type="button" className={`tab-btn ${mode === "register" ? "active" : ""}`}
              onClick={() => setMode("register")} disabled={loading}>
              Register
            </button>
          </div>

          <div className="form-group">
            <label>Email</label>
            <input type="email" value={email} onChange={e => setEmail(e.target.value)}
              placeholder="you@example.com" required disabled={loading} />
          </div>

          {mode === "register" && (
            <div className="form-group">
              <label>Username</label>
              <input type="text" value={username} onChange={e => setUsername(e.target.value)}
                placeholder="Your username" required disabled={loading} />
            </div>
          )}

          <div className="form-group">
            <label>Password</label>
            <input type="password" value={password} onChange={e => setPassword(e.target.value)}
              placeholder="••••••••" required disabled={loading} />
          </div>

          {error && <div className="error-message">{error}</div>}

          <button type="submit" className="submit-btn" disabled={loading}>
            {loading ? "Loading..." : mode === "login" ? "Login" : "Register"}
          </button>
        </form>
      </div>
    </div>
  );
}
