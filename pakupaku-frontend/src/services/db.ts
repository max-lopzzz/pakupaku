/**
 * db.ts
 * ──────────────────────────────────────────────────────
 * SQLite initialisation for PakuPaku mobile (Capacitor).
 * Exports getDb() — always returns the same open connection.
 * Call runMigrations() once at app startup (in index.tsx).
 */

import { CapacitorSQLite, SQLiteConnection, SQLiteDBConnection } from "@capacitor-community/sqlite";
import { Capacitor } from "@capacitor/core";

const DB_NAME    = "pakupaku";
const DB_VERSION = 1;

// ── Module-level singleton ────────────────────────────────────────────────────
let _db: SQLiteDBConnection | null = null;
const _sqlite = new SQLiteConnection(CapacitorSQLite);

// ── Schema ────────────────────────────────────────────────────────────────────
// NOTE: PRAGMA is intentionally NOT in SCHEMA — it must be run outside a
// transaction (transaction:false), whereas CREATE TABLE runs inside one.
const SCHEMA = `
CREATE TABLE IF NOT EXISTS users (
  id                   TEXT PRIMARY KEY,
  username             TEXT NOT NULL UNIQUE,
  hashed_password      TEXT NOT NULL,
  weight_kg            REAL,
  height_cm            REAL,
  age                  INTEGER,
  birthday             TEXT,
  hormonal_profile     TEXT,
  hrt_type             TEXT,
  hrt_months           INTEGER,
  navy_profile         TEXT,
  waist_cm             REAL,
  neck_cm              REAL,
  hip_cm               REAL,
  activity_level       TEXT,
  goal                 TEXT,
  pace_kg_per_week     REAL,
  metabolic_conditions TEXT,
  body_fat_pct         REAL,
  bmr                  REAL,
  tdee                 REAL,
  target_kcal          REAL,
  protein_g            REAL,
  fat_g                REAL,
  carbs_g              REAL,
  uses_custom_goals    INTEGER NOT NULL DEFAULT 0,
  custom_kcal          REAL,
  custom_protein       REAL,
  custom_fat           REAL,
  custom_carbs         REAL,
  safe_mode            INTEGER NOT NULL DEFAULT 0,
  created_at           TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS food_logs (
  id          TEXT PRIMARY KEY,
  user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  fdc_id      INTEGER,
  recipe_id   TEXT,
  food_name   TEXT NOT NULL,
  brand_name  TEXT,
  amount_g    REAL NOT NULL,
  calories    REAL,
  protein_g   REAL,
  fat_g       REAL,
  carbs_g     REAL,
  fiber_g     REAL,
  sugar_g     REAL,
  sodium_mg   REAL,
  meal        TEXT NOT NULL,
  log_date    TEXT NOT NULL,
  logged_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS recipes (
  id              TEXT PRIMARY KEY,
  user_id         TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name            TEXT NOT NULL,
  description     TEXT,
  servings        REAL NOT NULL DEFAULT 1,
  total_calories  REAL,
  total_protein_g REAL,
  total_fat_g     REAL,
  total_carbs_g   REAL,
  total_fiber_g   REAL,
  created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS recipe_ingredients (
  id         TEXT PRIMARY KEY,
  recipe_id  TEXT NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
  fdc_id     INTEGER,
  food_name  TEXT NOT NULL,
  brand_name TEXT,
  amount_g   REAL NOT NULL,
  calories   REAL,
  protein_g  REAL,
  fat_g      REAL,
  carbs_g    REAL,
  fiber_g    REAL
);

CREATE TABLE IF NOT EXISTS body_measurements (
  id           TEXT PRIMARY KEY,
  user_id      TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  measured_at  TEXT NOT NULL,
  weight_kg    REAL,
  height_cm    REAL,
  waist_cm     REAL,
  neck_cm      REAL,
  hip_cm       REAL,
  body_fat_pct REAL
);

CREATE TABLE IF NOT EXISTS workout_logs (
  id              TEXT PRIMARY KEY,
  user_id         TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  log_date        TEXT NOT NULL,
  logged_at       TEXT NOT NULL DEFAULT (datetime('now')),
  name            TEXT,
  workout_type    TEXT,
  duration_min    REAL,
  intensity       TEXT,
  calories_burned REAL NOT NULL DEFAULT 0,
  source          TEXT NOT NULL DEFAULT 'tracker',
  notes           TEXT
);

CREATE INDEX IF NOT EXISTS idx_food_logs_user_date    ON food_logs(user_id, log_date);
CREATE INDEX IF NOT EXISTS idx_workout_logs_user_date ON workout_logs(user_id, log_date);
CREATE INDEX IF NOT EXISTS idx_measurements_user      ON body_measurements(user_id, measured_at);
CREATE INDEX IF NOT EXISTS idx_recipes_user           ON recipes(user_id);
CREATE INDEX IF NOT EXISTS idx_recipe_ingredients     ON recipe_ingredients(recipe_id);
`;

// ── Web-platform bootstrap ────────────────────────────────────────────────────
async function _bootWeb() {
  const { defineCustomElements } = await import("jeep-sqlite/loader");
  await defineCustomElements(window);
  await customElements.whenDefined("jeep-sqlite");
  await _sqlite.initWebStore();
}

// ── Public API ────────────────────────────────────────────────────────────────

/**
 * runMigrations — call once before rendering React (in index.tsx).
 * Opens / creates the SQLite database and ensures all tables exist.
 */
export async function runMigrations(): Promise<void> {
  if (Capacitor.getPlatform() === "web") {
    await _bootWeb();
  }

  const consistent = await _sqlite.checkConnectionsConsistency();
  const isConn = (await _sqlite.isConnection(DB_NAME, false)).result;

  if (consistent.result && isConn) {
    _db = await _sqlite.retrieveConnection(DB_NAME, false);
  } else {
    _db = await _sqlite.createConnection(
      DB_NAME, false, "no-encryption", DB_VERSION, false
    );
  }

  await _db.open();

  // PRAGMA must be executed outside a transaction on Android
  await _db.execute("PRAGMA foreign_keys = ON;", false);

  // Run schema migrations inside a transaction (the default)
  await _db.execute(SCHEMA, true);
}

/**
 * getDb — returns the open SQLiteDBConnection.
 * Always call runMigrations() before using this.
 */
export function getDb(): SQLiteDBConnection {
  if (!_db) throw new Error("DB not initialised — call runMigrations() first.");
  return _db;
}
