import { useState } from "react";
import "./Settings.css";

interface SettingsProps {
  userProfile: any;
  onBack: () => void;
  onLogout: () => void;
  onProfileUpdate: (updated: any) => void;
}

function authHeaders(extra: Record<string, string> = {}) {
  const token = localStorage.getItem("token");
  return { Authorization: token ? `Bearer ${token}` : "", ...extra };
}

async function errorDetail(res: Response, fallback: string): Promise<string> {
  const body = await res.json().catch(() => null);
  return typeof body?.detail === "string" ? body.detail : fallback;
}

export default function Settings({ userProfile, onBack, onLogout, onProfileUpdate }: SettingsProps) {
  // ── Safe mode ──────────────────────────────────────────────────────────────
  const [safeMode, setSafeMode]       = useState<boolean>(!!userProfile?.safe_mode);
  const [safeSaving, setSafeSaving]   = useState(false);

  const handleSafeModeToggle = async (checked: boolean) => {
    setSafeSaving(true);
    try {
      const res = await fetch("/users/me", {
        method: "PATCH",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ safe_mode: checked }),
      });
      if (!res.ok) throw new Error(await errorDetail(res, "Failed to update safe mode."));
      const result = await res.json();
      setSafeMode(checked);
      onProfileUpdate(result);
    } catch { /* non-fatal */ } finally {
      setSafeSaving(false);
    }
  };

  // ── Change username ────────────────────────────────────────────────────────
  const [newUsername,     setNewUsername]     = useState("");
  const [usernameMsg,     setUsernameMsg]     = useState("");
  const [usernameError,   setUsernameError]   = useState("");
  const [usernameSaving,  setUsernameSaving]  = useState(false);

  const handleUsernameChange = async () => {
    setUsernameMsg("");
    setUsernameError("");
    if (!newUsername.trim()) { setUsernameError("Username cannot be empty."); return; }
    setUsernameSaving(true);
    try {
      const res = await fetch("/users/me", {
        method: "PATCH",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ username: newUsername.trim() }),
      });
      if (!res.ok) throw new Error(await errorDetail(res, "Failed to update username."));
      const result = await res.json();
      onProfileUpdate(result);
      setUsernameMsg("Username updated!");
      setNewUsername("");
    } catch (e: any) {
      setUsernameError(e.message || "Failed to update username.");
    } finally {
      setUsernameSaving(false);
    }
  };

  // ── Change password ────────────────────────────────────────────────────────
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword,    setNewPassword]    = useState("");
  const [confirmPw,      setConfirmPw]      = useState("");
  const [passwordMsg,    setPasswordMsg]    = useState("");
  const [passwordError,  setPasswordError]  = useState("");
  const [passwordSaving, setPasswordSaving] = useState(false);

  const handlePasswordChange = async () => {
    setPasswordMsg("");
    setPasswordError("");
    if (!currentPassword.trim()) { setPasswordError("Enter your current password."); return; }
    if (!newPassword.trim()) { setPasswordError("Password cannot be empty."); return; }
    if (newPassword !== confirmPw) { setPasswordError("Passwords do not match."); return; }
    setPasswordSaving(true);
    try {
      const res = await fetch("/users/me/change-password", {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          current_password: currentPassword,
          new_password:      newPassword,
        }),
      });
      if (!res.ok) throw new Error(await errorDetail(res, "Failed to update password."));
      setPasswordMsg("Password updated!");
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPw("");
    } catch (e: any) {
      setPasswordError(e.message || "Failed to update password.");
    } finally {
      setPasswordSaving(false);
    }
  };

  // ── Export data ────────────────────────────────────────────────────────────
  const [exportLoading, setExportLoading] = useState(false);
  const [exportError, setExportError] = useState("");

  const handleExport = async () => {
    setExportLoading(true);
    setExportError("");
    try {
      const res = await fetch("/users/me/export", { headers: authHeaders() });
      if (!res.ok) throw new Error(await errorDetail(res, "Failed to export data."));
      const data = await res.json();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement("a");
      a.href     = url;
      a.download = "pakupaku-export.json";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e: any) {
      setExportError(e.message || "Failed to export data.");
    } finally {
      setExportLoading(false);
    }
  };

  // ── Delete account ─────────────────────────────────────────────────────────
  const [deleteError, setDeleteError] = useState("");

  const handleDeleteAccount = async () => {
    if (!window.confirm("This will permanently delete your account and all data. Are you sure?")) return;
    setDeleteError("");
    try {
      const res = await fetch("/users/me", { method: "DELETE", headers: authHeaders() });
      if (!res.ok) throw new Error(await errorDetail(res, "Failed to delete account."));
      onLogout();
    } catch (e: any) {
      setDeleteError(e.message || "Failed to delete account.");
    }
  };

  return (
    <div className="settings-root">
      <div className="settings-container">
        {/* Header */}
        <header className="settings-header">
          <button type="button" className="back-button" onClick={onBack}>← Back</button>
          <div>
            <h1 className="settings-title">Settings</h1>
          </div>
        </header>

        {/* Support section */}
        <section className="settings-section">
          <h2 className="settings-section-title">Support</h2>
          <div className="settings-card">
            <button
              type="button"
              className="kofi-button"
              onClick={() => window.open("https://ko-fi.com/P5P61TI6BS", "_blank")}
            >
              Support PakuPaku on Ko-fi ☕
            </button>
          </div>
        </section>

        {/* Wellbeing section */}
        <section className="settings-section">
          <h2 className="settings-section-title">Wellbeing</h2>
          <div className="settings-card">
            <div className="settings-row">
              <div className="settings-row-info">
                <span className="settings-row-label">Safe mode</span>
                <span className="settings-row-desc">Hides calorie counts and macro numbers that may be triggering.</span>
              </div>
              <div className="settings-row-control">
                {safeSaving && <span className="settings-spinner" aria-label="Saving…" />}
                <label className="toggle-switch">
                  <input
                    type="checkbox"
                    checked={safeMode}
                    disabled={safeSaving}
                    onChange={e => handleSafeModeToggle(e.target.checked)}
                  />
                  <span className="toggle-track">
                    <span className="toggle-thumb" />
                  </span>
                </label>
              </div>
            </div>
          </div>
        </section>

        {/* Account section */}
        <section className="settings-section">
          <h2 className="settings-section-title">Account</h2>
          <div className="settings-card">

            {/* Change username */}
            <div className="settings-sub-section">
              <h3 className="settings-sub-title">Change username</h3>
              <p className="settings-current-value">Current: <strong>{userProfile?.username ?? "—"}</strong></p>
              <div className="settings-inline-form">
                <input
                  type="text"
                  className="settings-input"
                  placeholder="New username"
                  value={newUsername}
                  onChange={e => setNewUsername(e.target.value)}
                  onKeyDown={e => e.key === "Enter" && handleUsernameChange()}
                />
                <button
                  type="button"
                  className="settings-save-button"
                  onClick={handleUsernameChange}
                  disabled={usernameSaving}
                >
                  {usernameSaving ? "Saving…" : "Save"}
                </button>
              </div>
              {usernameMsg   && <p className="settings-success">{usernameMsg}</p>}
              {usernameError && <p className="settings-error">{usernameError}</p>}
            </div>

            <div className="settings-divider" />

            {/* Change password */}
            <div className="settings-sub-section">
              <h3 className="settings-sub-title">Change password</h3>
              <div className="settings-inline-form settings-inline-form--column">
                <input
                  type="password"
                  className="settings-input"
                  placeholder="Current password"
                  value={currentPassword}
                  onChange={e => setCurrentPassword(e.target.value)}
                />
                <input
                  type="password"
                  className="settings-input"
                  placeholder="New password"
                  value={newPassword}
                  onChange={e => setNewPassword(e.target.value)}
                />
                <input
                  type="password"
                  className="settings-input"
                  placeholder="Confirm new password"
                  value={confirmPw}
                  onChange={e => setConfirmPw(e.target.value)}
                  onKeyDown={e => e.key === "Enter" && handlePasswordChange()}
                />
                <button
                  type="button"
                  className="settings-save-button"
                  onClick={handlePasswordChange}
                  disabled={passwordSaving}
                >
                  {passwordSaving ? "Saving…" : "Update password"}
                </button>
              </div>
              {passwordMsg   && <p className="settings-success">{passwordMsg}</p>}
              {passwordError && <p className="settings-error">{passwordError}</p>}
            </div>

            <div className="settings-divider" />

            {/* Export data */}
            <div className="settings-sub-section">
              <h3 className="settings-sub-title">Export my data</h3>
              <p className="settings-row-desc">Download all your PakuPaku data as a JSON file.</p>
              <button
                type="button"
                className="settings-secondary-button"
                onClick={handleExport}
                disabled={exportLoading}
              >
                {exportLoading ? "Exporting…" : "Export data"}
              </button>
              {exportError && <p className="settings-error">{exportError}</p>}
            </div>

            <div className="settings-divider" />

            {/* Log out */}
            <div className="settings-sub-section">
              <button type="button" className="settings-secondary-button" onClick={onLogout}>
                Log out
              </button>
            </div>

            <div className="settings-divider" />

            {/* Delete account */}
            <div className="settings-sub-section">
              <h3 className="settings-sub-title">Delete all data</h3>
              <p className="settings-row-desc">Permanently deletes your account and all associated data. This cannot be undone.</p>
              <button
                type="button"
                className="settings-danger-button"
                onClick={handleDeleteAccount}
              >
                Delete account
              </button>
              {deleteError && <p className="settings-error">{deleteError}</p>}
            </div>

          </div>
        </section>

        {/* About section */}
        <section className="settings-section">
          <h2 className="settings-section-title">About</h2>
          <div className="settings-card settings-about">
            <p className="about-app-name">PakuPaku</p>
            <p className="about-version">Version 1.0.0</p>
            <p className="about-made-with">Made with ♥</p>
          </div>
        </section>
      </div>
    </div>
  );
}
