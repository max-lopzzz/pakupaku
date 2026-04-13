/**
 * auth.ts
 * ──────────────────────────────────────────────────────
 * Single-device authentication for PakuPaku mobile.
 * No email, no JWT — one account per device, Web Crypto
 * PBKDF2 for password hashing (built-in to every WebView —
 * no extra bundle weight, runs off the JS thread).
 * Session stored in memory + localStorage.
 */

import { getDb } from "./db";

// ── PBKDF2 password helpers ───────────────────────────────────────────────────

const PBKDF2_ITERATIONS = 100_000;
const HASH_ALGO = "SHA-256";

function _buf2hex(buf: ArrayBuffer): string {
  return Array.from(new Uint8Array(buf))
    .map(b => b.toString(16).padStart(2, "0"))
    .join("");
}

function _hex2buf(hex: string): Uint8Array {
  const arr = new Uint8Array(hex.length / 2);
  for (let i = 0; i < arr.length; i++)
    arr[i] = parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  return arr;
}

/** Returns "salt:hash" — both as hex strings. */
async function _hashPassword(password: string): Promise<string> {
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const keyMaterial = await crypto.subtle.importKey(
    "raw", new TextEncoder().encode(password), "PBKDF2", false, ["deriveBits"]
  );
  const bits = await crypto.subtle.deriveBits(
    { name: "PBKDF2", salt, iterations: PBKDF2_ITERATIONS, hash: HASH_ALGO },
    keyMaterial, 256
  );
  return `${_buf2hex(salt.buffer)}:${_buf2hex(bits)}`;
}

/** Returns true if password matches the stored "salt:hash" string. */
async function _verifyPassword(password: string, stored: string): Promise<boolean> {
  const [saltHex, hashHex] = stored.split(":");
  if (!saltHex || !hashHex) return false;
  const salt = _hex2buf(saltHex);
  const keyMaterial = await crypto.subtle.importKey(
    "raw", new TextEncoder().encode(password), "PBKDF2", false, ["deriveBits"]
  );
  const bits = await crypto.subtle.deriveBits(
    { name: "PBKDF2", salt, iterations: PBKDF2_ITERATIONS, hash: HASH_ALGO },
    keyMaterial, 256
  );
  return _buf2hex(bits) === hashHex;
}

// ── Types ─────────────────────────────────────────────────────────────────────

export interface UserProfile {
  id: string;
  username: string;
  // biometrics
  weight_kg:            number | null;
  height_cm:            number | null;
  age:                  number | null;
  birthday:             string | null;
  // hormonal profile
  hormonal_profile:     string | null;
  hrt_type:             string | null;
  hrt_months:           number | null;
  // body shape
  navy_profile:         string | null;
  waist_cm:             number | null;
  neck_cm:              number | null;
  hip_cm:               number | null;
  // activity / goal
  activity_level:       string | null;
  goal:                 string | null;
  pace_kg_per_week:     number | null;
  metabolic_conditions: string | null;
  // calculated targets
  body_fat_pct:         number | null;
  bmr:                  number | null;
  tdee:                 number | null;
  target_kcal:          number | null;
  protein_g:            number | null;
  fat_g:                number | null;
  carbs_g:              number | null;
  // custom goals
  uses_custom_goals:    number;   // 0 or 1 (SQLite has no boolean)
  custom_kcal:          number | null;
  custom_protein:       number | null;
  custom_fat:           number | null;
  custom_carbs:         number | null;
  safe_mode:            number;
  // email_verified is always true on mobile (no email flow)
  email_verified:       boolean;
}

// ── In-memory session ─────────────────────────────────────────────────────────

let _currentUserId: string | null = null;

// ── Helpers ───────────────────────────────────────────────────────────────────

function _uuid(): string {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  // Fallback for older Android WebViews
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, c => {
    const r = (Math.random() * 16) | 0;
    return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
  });
}

function _rowToProfile(row: any): UserProfile {
  return {
    ...row,
    email_verified: true,    // always verified on-device
  };
}

async function _getUserById(id: string): Promise<UserProfile | null> {
  const db = getDb();
  const res = await db.query("SELECT * FROM users WHERE id = ?", [id]);
  if (!res.values || res.values.length === 0) return null;
  return _rowToProfile(res.values[0]);
}

// ── Public API ────────────────────────────────────────────────────────────────

/**
 * Register a new account on this device.
 * Throws if an account already exists (one account per device).
 */
export async function register(
  username: string,
  password: string
): Promise<UserProfile> {
  const db = getDb();

  // Check for existing account
  const existing = await db.query("SELECT id FROM users LIMIT 1");
  if (existing.values && existing.values.length > 0) {
    throw new Error("An account already exists on this device. Please log in.");
  }

  const id             = _uuid();
  const hashedPassword = await _hashPassword(password);

  await db.run(
    "INSERT INTO users (id, username, hashed_password) VALUES (?, ?, ?)",
    [id, username.trim(), hashedPassword]
  );

  _currentUserId = id;
  localStorage.setItem("userId", id);
  localStorage.setItem("token", "local");

  return (await _getUserById(id))!;
}

/**
 * Log in with username + password.
 * Throws on bad credentials.
 */
export async function login(
  username: string,
  password: string
): Promise<UserProfile> {
  const db = getDb();
  const res = await db.query(
    "SELECT * FROM users WHERE username = ?",
    [username.trim()]
  );

  if (!res.values || res.values.length === 0) {
    throw new Error("Incorrect username or password.");
  }

  const row = res.values[0];
  const valid = await _verifyPassword(password, row.hashed_password);
  if (!valid) throw new Error("Incorrect username or password.");

  _currentUserId = row.id;
  localStorage.setItem("userId", row.id);
  localStorage.setItem("token", "local");

  return _rowToProfile(row);
}

/**
 * Clear the session.
 */
export async function logout(): Promise<void> {
  _currentUserId = null;
  localStorage.removeItem("userId");
  localStorage.removeItem("token");
}

/**
 * Return the current user from SQLite (or null if not logged in).
 * Restores the session from localStorage across page reloads.
 */
export async function getSession(): Promise<UserProfile | null> {
  const id = _currentUserId || localStorage.getItem("userId");
  if (!id) return null;
  const user = await _getUserById(id);
  if (user) _currentUserId = id;
  return user;
}

/**
 * Return the current user ID or throw if not logged in.
 */
export function getCurrentUserId(): string {
  const id = _currentUserId || localStorage.getItem("userId");
  if (!id) throw new Error("Not logged in.");
  return id;
}

/**
 * Patch the current user profile in SQLite.
 * Pass only the fields you want to update.
 */
export async function updateUserProfile(
  patch: Partial<Omit<UserProfile, "id" | "email_verified">>
): Promise<UserProfile> {
  const id = getCurrentUserId();
  const db = getDb();

  const cols   = Object.keys(patch);
  const values = Object.values(patch);

  if (cols.length === 0) return (await _getUserById(id))!;

  const setClause = cols.map(c => `${c} = ?`).join(", ");
  await db.run(
    `UPDATE users SET ${setClause} WHERE id = ?`,
    [...values, id]
  );

  return (await _getUserById(id))!;
}

/**
 * Change the current user's password.
 * Hashes the new password with PBKDF2 and updates the DB.
 */
export async function changePassword(newPassword: string): Promise<void> {
  const hashed = await _hashPassword(newPassword);
  const id = getCurrentUserId();
  const db = getDb();
  await db.run("UPDATE users SET hashed_password = ? WHERE id = ?", [hashed, id]);
}
