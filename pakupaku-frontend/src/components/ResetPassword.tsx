import { useState } from "react";
import "./Login.css";
import { apiFetch } from "../apiBase";

interface ResetPasswordProps {
  token: string;
  onDone: () => void;
}

export default function ResetPassword({ token, onDone }: ResetPasswordProps) {
  const [password, setPassword]               = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError]     = useState("");
  const [loading, setLoading] = useState(false);
  const [done, setDone]       = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (password !== confirmPassword) {
      setError("Passwords don't match.");
      return;
    }

    setLoading(true);
    try {
      const res = await apiFetch("/auth/reset-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, new_password: password }),
      });

      if (!res.ok) {
        const errorData = await res.json().catch(() => null);
        setError(
          typeof errorData?.detail === "string"
            ? errorData.detail
            : "That reset link is invalid or has expired."
        );
        return;
      }

      setDone(true);
    } catch (err) {
      console.error("Reset password error:", err);
      setError("Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  if (done) {
    return (
      <div className="login-root">
        <div className="login-card">
          <h1 className="login-title">Password reset 🎉</h1>
          <p className="login-subtitle">Your password has been changed.</p>
          <div className="login-form">
            <button type="button" className="submit-btn" onClick={onDone}>
              Back to login
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="login-root">
      <div className="login-card">
        <h1 className="login-title">Choose a new password 🔑</h1>

        <form onSubmit={handleSubmit} className="login-form">
          <div className="form-group">
            <label>New password</label>
            <input type="password" value={password} onChange={e => setPassword(e.target.value)}
              placeholder="••••••••" required minLength={8} disabled={loading} />
          </div>

          <div className="form-group">
            <label>Confirm new password</label>
            <input type="password" value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)}
              placeholder="••••••••" required minLength={8} disabled={loading} />
          </div>

          {error && <div className="error-message">{error}</div>}

          <button type="submit" className="submit-btn" disabled={loading}>
            {loading ? "Saving..." : "Reset password"}
          </button>

          <button type="button" className="link-btn" onClick={onDone}>
            Back to login
          </button>
        </form>
      </div>
    </div>
  );
}
