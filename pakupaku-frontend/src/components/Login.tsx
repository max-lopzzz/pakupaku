import { useState } from "react";
import "./Login.css";
import { apiFetch } from "../apiBase";

interface LoginProps {
  onLoginSuccess: () => void;
}

type Mode = "login" | "register" | "forgotPassword";

export default function Login({ onLoginSuccess }: LoginProps) {
  const [mode, setMode]               = useState<Mode>("login");
  const [email, setEmail]             = useState("");
  const [username, setUsername]       = useState("");
  const [password, setPassword]       = useState("");
  const [error, setError]   = useState("");
  const [loading, setLoading] = useState(false);
  const [resetSent, setResetSent] = useState(false);

  const switchMode = (next: Mode) => {
    setMode(next);
    setError("");
    setResetSent(false);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      if (mode === "forgotPassword") {
        const res = await apiFetch("/auth/forgot-password", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email }),
        });
        if (!res.ok) {
          setError("Something went wrong. Please try again.");
          return;
        }
        // Same response whether or not the email exists — the UI doesn't
        // reveal that either.
        setResetSent(true);
        return;
      }

      const endpoint = mode === "login" ? "/auth/login" : "/auth/register";
      const body =
        mode === "login"
          ? { email, password }
          : { email, username, password };

      const res = await apiFetch(endpoint, {
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

        {mode !== "forgotPassword" && (
          <div className="tab-buttons">
            <button type="button" className={`tab-btn ${mode === "login" ? "active" : ""}`}
              onClick={() => switchMode("login")} disabled={loading}>
              Login
            </button>
            <button type="button" className={`tab-btn ${mode === "register" ? "active" : ""}`}
              onClick={() => switchMode("register")} disabled={loading}>
              Register
            </button>
          </div>
        )}

        {mode === "forgotPassword" && resetSent ? (
          <div className="login-form">
            <p>If an account exists for that email, we've sent a link to reset your password.</p>
            <button type="button" className="submit-btn" onClick={() => switchMode("login")}>
              Back to login
            </button>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="login-form">
            {mode === "forgotPassword" && (
              <p>Enter your email and we'll send you a link to reset your password.</p>
            )}

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

            {mode !== "forgotPassword" && (
              <div className="form-group">
                <label>Password</label>
                <input type="password" value={password} onChange={e => setPassword(e.target.value)}
                  placeholder="••••••••" required disabled={loading} />
              </div>
            )}

            {mode === "login" && (
              <button type="button" className="link-btn" onClick={() => switchMode("forgotPassword")}>
                Forgot password?
              </button>
            )}

            {error && <div className="error-message">{error}</div>}

            <button type="submit" className="submit-btn" disabled={loading}>
              {loading
                ? "Loading..."
                : mode === "login" ? "Login"
                : mode === "register" ? "Register"
                : "Send reset link"}
            </button>

            {mode === "forgotPassword" && (
              <button type="button" className="link-btn" onClick={() => switchMode("login")}>
                Back to login
              </button>
            )}
          </form>
        )}
      </div>
    </div>
  );
}
