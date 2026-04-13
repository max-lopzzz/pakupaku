/**
 * api.ts
 * ──────────────────────────────────────────────────────
 * Drop-in replacement for all fetch() calls in the components.
 * Talks to the local SQLite DB (via db.ts + auth.ts) instead of
 * the Python backend. USDA food search still goes to the internet.
 */

import { getDb } from "./db";
import {
  login as _login,
  register as _register,
  logout as _logout,
  getSession,
  getCurrentUserId,
  updateUserProfile,
  UserProfile,
} from "./auth";
import {
  calcBodyFatNavy,
  calcBodyFatBmi,
  calcBmr,
  interpolateBmrHrt,
  hrtNavyBlendT,
  applyMetabolicConditions,
  calcTdee,
  calcGoalAdjustment,
  calcMacros,
} from "./nutritionCalculator";

// ── UUID ──────────────────────────────────────────────────────────────────────

function uuid(): string {
  if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID();
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, c => {
    const r = (Math.random() * 16) | 0;
    return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
  });
}

// ── USDA ──────────────────────────────────────────────────────────────────────

const USDA_BASE = "https://api.nal.usda.gov/fdc/v1";
const USDA_KEY  = process.env.REACT_APP_USDA_API_KEY ?? "";

export async function apiFoodSearch(
  query: string,
  pageSize = 50
): Promise<{ foods: any[] }> {
  const params = new URLSearchParams({
    query,
    pageSize: String(pageSize),
    api_key:  USDA_KEY,
  });
  const res = await fetch(`${USDA_BASE}/foods/search?${params}`);
  if (!res.ok) throw new Error("USDA search failed");
  return res.json();
}

export async function apiFoodDetail(
  fdcId: number
): Promise<{ portions: { unit: string; grams_per_unit: number }[] }> {
  const res = await fetch(`${USDA_BASE}/food/${fdcId}?api_key=${USDA_KEY}`);
  if (!res.ok) throw new Error("USDA food detail failed");
  const food = await res.json();

  // Port of usda.py extract_nutrients() portion parsing
  const UNIT_ALIASES: Record<string, string> = {
    c: "cup", cup: "cup", cups: "cup",
    tbs: "tbsp", tbsp: "tbsp", tablespoon: "tbsp", tablespoons: "tbsp",
    tsp: "tsp", teaspoon: "tsp", teaspoons: "tsp",
    oz: "oz", ounce: "oz", ounces: "oz",
    g: "g", gram: "g", grams: "g",
    ml: "ml", milliliter: "ml", milliliters: "ml",
    millilitre: "ml", millilitres: "ml",
  };
  const DENYLIST = new Set(["individual","school","guideline","specified","container","quantity","amount","serving"]);

  function normalise(raw: string): string | null {
    const key = UNIT_ALIASES[raw] ?? raw;
    if (key && !DENYLIST.has(key) && key.length <= 20) return key;
    return null;
  }

  function unitAndGrams(p: any): [string | null, number | null] {
    const gramWeight = p.gramWeight;
    if (!gramWeight) return [null, null];
    const unitInfo = p.measureUnit ?? {};
    const unitId   = unitInfo.id;
    const amount   = parseFloat(p.amount ?? "1") || 1;

    // Path A: real measureUnit ID (Foundation)
    if (unitId && unitId !== 9999) {
      const raw = (unitInfo.name ?? unitInfo.abbreviation ?? "").trim().toLowerCase();
      const key = normalise(raw);
      if (key && amount > 0) return [key, Math.round((gramWeight / Math.max(amount, 0.001)) * 100) / 100];
    }

    // Path B: Survey FNDDS — portionDescription
    const desc = (p.portionDescription ?? "").trim();
    if (desc) {
      const m = desc.match(/^(\d+(?:\/\d+)?(?:\.\d+)?)\s+(fl\s+oz|[a-z]+)/i);
      if (m) {
        let amt = m[1].includes("/")
          ? parseFloat(m[1].split("/")[0]) / parseFloat(m[1].split("/")[1])
          : parseFloat(m[1]);
        const key = normalise(m[2].trim().toLowerCase());
        if (key && amt > 0) return [key, Math.round((gramWeight / amt) * 100) / 100];
      }
    }

    // Path C: SR Legacy — modifier
    const modifier = (p.modifier ?? "").trim();
    if (modifier && !/^\d+$/.test(modifier)) {
      const clean = modifier.replace(/\s*\(.*\)/, "").trim().toLowerCase();
      for (const candidate of [clean, clean.split(" ")[0]].filter(Boolean)) {
        const key = normalise(candidate);
        if (key && amount > 0) return [key, Math.round((gramWeight / Math.max(amount, 0.001)) * 100) / 100];
      }
    }

    return [null, null];
  }

  const portions: { unit: string; grams_per_unit: number }[] = [];
  const seen = new Set<string>();

  for (const p of food.foodPortions ?? []) {
    const [unit, gpg] = unitAndGrams(p);
    if (unit && gpg && !seen.has(unit)) {
      portions.push({ unit, grams_per_unit: gpg });
      seen.add(unit);
    }
  }

  // Branded serving size
  const ss = food.servingSize;
  const su = (food.servingSizeUnit ?? "").trim().toLowerCase();
  if (ss && su && su !== "g" && !seen.has(su)) {
    portions.push({ unit: su, grams_per_unit: Math.round(parseFloat(ss) * 100) / 100 });
  }

  return { portions };
}

// ── Auth ──────────────────────────────────────────────────────────────────────

export type { UserProfile };

export async function apiLogin(username: string, password: string): Promise<void> {
  await _login(username, password);
}

export async function apiRegister(username: string, password: string): Promise<void> {
  await _register(username, password);
}

export async function apiLogout(): Promise<void> {
  await _logout();
}

export async function apiGetMe(): Promise<UserProfile | null> {
  return getSession();
}

// ── Onboarding ────────────────────────────────────────────────────────────────

export interface OnboardingCalcPayload {
  weight_kg:            number;
  height_cm:            number;
  age:                  number;
  birthday?:            string;
  hormonal_profile:     string;
  hrt_type?:            string | null;
  hrt_months?:          number | null;
  use_bmi_mode:         boolean;
  navy_profile:         string;
  waist_cm:             number | null;
  neck_cm:              number | null;
  hip_cm?:              number | null;
  activity_level:       string;
  goal:                 string;
  pace_kg_per_week:     number;
  metabolic_conditions: string[];
  safe_mode?:           boolean;
}

export async function apiOnboardingCalculate(
  p: OnboardingCalcPayload
): Promise<any> {
  // Calculate body fat percentage based on mode
  let bodyFatPct: number;
  
  if (p.use_bmi_mode) {
    // Use BMI-based estimation (Deurenberg formula)
    const bmi = p.weight_kg / ((p.height_cm / 100) ** 2);
    bodyFatPct = calcBodyFatBmi(bmi, p.age, p.hormonal_profile);
  } else {
    // Use Navy method with circumference measurements
    let navyBlendT: number | null = null;
    if (p.navy_profile === "blend" && p.hrt_type && p.hrt_months != null) {
      navyBlendT = hrtNavyBlendT(p.hrt_type, p.hrt_months);
    }
    bodyFatPct = calcBodyFatNavy(
      p.height_cm, p.waist_cm ?? 0, p.neck_cm ?? 0, p.hip_cm ?? null,
      p.navy_profile as any, navyBlendT
    );
  }

  let bmr: number;
  if (p.hormonal_profile === "hrt" && p.hrt_type && p.hrt_months != null) {
    bmr = interpolateBmrHrt(
      p.weight_kg, p.height_cm, p.age,
      p.hrt_type, p.hrt_months, bodyFatPct
    );
  } else {
    bmr = calcBmr(p.weight_kg, p.height_cm, p.age, p.hormonal_profile, bodyFatPct);
  }

  const condResult   = applyMetabolicConditions(bmr, p.metabolic_conditions ?? []);
  const adjustedBmr  = condResult.adjusted_bmr;
  const tdee         = calcTdee(adjustedBmr, p.activity_level);
  const [goalKcal]   = calcGoalAdjustment(p.goal, p.pace_kg_per_week);
  const targetKcal   = tdee + goalKcal;
  const macros       = calcMacros(targetKcal, p.weight_kg, bodyFatPct, p.goal);

  // Auto-enable safe mode if eating disorder history is selected
  const hasEatingDisorderHistory = (p.metabolic_conditions ?? []).includes("eating_disorder_history");
  const safeModeEnabled = p.safe_mode ?? hasEatingDisorderHistory;

  const patch: any = {
    weight_kg:            p.weight_kg,
    height_cm:            p.height_cm,
    age:                  p.age,
    birthday:             p.birthday ?? null,
    hormonal_profile:     p.hormonal_profile,
    hrt_type:             p.hrt_type ?? null,
    hrt_months:           p.hrt_months ?? null,
    navy_profile:         p.navy_profile,
    waist_cm:             p.waist_cm,
    neck_cm:              p.neck_cm,
    hip_cm:               p.hip_cm ?? null,
    activity_level:       p.activity_level,
    goal:                 p.goal,
    pace_kg_per_week:     p.pace_kg_per_week,
    metabolic_conditions: (p.metabolic_conditions ?? []).join(","),
    body_fat_pct:         Math.round(bodyFatPct * 10) / 10,
    bmr:                  Math.round(bmr),
    tdee:                 Math.round(tdee),
    target_kcal:          Math.round(targetKcal),
    protein_g:            macros.protein_g,
    fat_g:                macros.fat_g,
    carbs_g:              macros.carbs_g,
    uses_custom_goals:    0,
    safe_mode:            safeModeEnabled ? 1 : 0,
  };

  await updateUserProfile(patch);

  return {
    ...patch,
    condition_notes:  condResult.condition_notes,
    requires_consult: condResult.requires_consult,
  };
}

export async function apiOnboardingCustom(payload: {
  custom_kcal:    number;
  custom_protein: number;
  custom_fat:     number;
  custom_carbs:   number;
}): Promise<UserProfile> {
  return updateUserProfile({
    uses_custom_goals: 1,
    custom_kcal:       payload.custom_kcal,
    custom_protein:    payload.custom_protein,
    custom_fat:        payload.custom_fat,
    custom_carbs:      payload.custom_carbs,
  });
}

// ── Food logs ─────────────────────────────────────────────────────────────────

export interface FoodLogRow {
  id:         string;
  fdc_id:     number | null;
  recipe_id:  string | null;
  food_name:  string;
  brand_name: string | null;
  amount_g:   number;
  calories:   number | null;
  protein_g:  number | null;
  fat_g:      number | null;
  carbs_g:    number | null;
  fiber_g:    number | null;
  sugar_g:    number | null;
  sodium_mg:  number | null;
  meal:       string;
  log_date:   string;
  logged_at:  string;
}

export async function apiGetLogs(logDate: string): Promise<FoodLogRow[]> {
  const db  = getDb();
  const uid = getCurrentUserId();
  const res = await db.query(
    "SELECT * FROM food_logs WHERE user_id = ? AND log_date = ? ORDER BY logged_at",
    [uid, logDate]
  );
  return res.values ?? [];
}

export async function apiCreateLog(payload: Omit<FoodLogRow, "id" | "logged_at">): Promise<FoodLogRow> {
  const db  = getDb();
  const uid = getCurrentUserId();
  const id  = uuid();
  const now = new Date().toISOString();

  await db.run(
    `INSERT INTO food_logs
      (id, user_id, fdc_id, recipe_id, food_name, brand_name,
       amount_g, calories, protein_g, fat_g, carbs_g, fiber_g,
       sugar_g, sodium_mg, meal, log_date, logged_at)
     VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)`,
    [id, uid,
     payload.fdc_id ?? null, payload.recipe_id ?? null,
     payload.food_name, payload.brand_name ?? null,
     payload.amount_g,
     payload.calories ?? null, payload.protein_g ?? null,
     payload.fat_g ?? null, payload.carbs_g ?? null,
     payload.fiber_g ?? null, payload.sugar_g ?? null,
     payload.sodium_mg ?? null,
     payload.meal, payload.log_date, now]
  );

  return { ...payload, id, logged_at: now };
}

export async function apiDeleteLog(logId: string): Promise<void> {
  const db  = getDb();
  const uid = getCurrentUserId();
  await db.run(
    "DELETE FROM food_logs WHERE id = ? AND user_id = ?",
    [logId, uid]
  );
}

// ── Recipes ───────────────────────────────────────────────────────────────────

export interface RecipeIngredient {
  id?:        string;
  recipe_id?: string;
  fdc_id:     number | null;
  food_name:  string;
  brand_name: string | null;
  amount_g:   number;
  calories:   number | null;
  protein_g:  number | null;
  fat_g:      number | null;
  carbs_g:    number | null;
  fiber_g:    number | null;
}

export interface RecipeResponse {
  id:              string;
  name:            string;
  description:     string | null;
  servings:        number;
  total_calories:  number | null;
  total_protein_g: number | null;
  total_fat_g:     number | null;
  total_carbs_g:   number | null;
  total_fiber_g:   number | null;
  created_at:      string;
  ingredients:     RecipeIngredient[];
}

function _computeTotals(ingredients: RecipeIngredient[], servings: number) {
  const safeSum = (field: keyof RecipeIngredient) => {
    const vals = ingredients
      .map(i => i[field] as number | null)
      .filter(v => v != null) as number[];
    if (vals.length === 0) return null;
    return Math.round((vals.reduce((a, b) => a + b, 0) / servings) * 100) / 100;
  };
  return {
    total_calories:  safeSum("calories"),
    total_protein_g: safeSum("protein_g"),
    total_fat_g:     safeSum("fat_g"),
    total_carbs_g:   safeSum("carbs_g"),
    total_fiber_g:   safeSum("fiber_g"),
  };
}

async function _fetchRecipeWithIngredients(recipeId: string): Promise<RecipeResponse> {
  const db   = getDb();
  const rRes = await db.query("SELECT * FROM recipes WHERE id = ?", [recipeId]);
  const iRes = await db.query(
    "SELECT * FROM recipe_ingredients WHERE recipe_id = ? ORDER BY rowid",
    [recipeId]
  );
  return { ...(rRes.values![0]), ingredients: iRes.values ?? [] };
}

export async function apiListRecipes(): Promise<RecipeResponse[]> {
  const db  = getDb();
  const uid = getCurrentUserId();
  const rRes = await db.query(
    "SELECT * FROM recipes WHERE user_id = ? ORDER BY created_at DESC",
    [uid]
  );
  const recipes = rRes.values ?? [];

  const result: RecipeResponse[] = [];
  for (const r of recipes) {
    const iRes = await db.query(
      "SELECT * FROM recipe_ingredients WHERE recipe_id = ? ORDER BY rowid",
      [r.id]
    );
    result.push({ ...r, ingredients: iRes.values ?? [] });
  }
  return result;
}

export async function apiCreateRecipe(payload: {
  name:        string;
  description?: string | null;
  servings:    number;
  ingredients: RecipeIngredient[];
}): Promise<RecipeResponse> {
  const db  = getDb();
  const uid = getCurrentUserId();
  const id  = uuid();
  const now = new Date().toISOString();

  const totals = _computeTotals(payload.ingredients, payload.servings);

  await db.run(
    `INSERT INTO recipes
       (id, user_id, name, description, servings,
        total_calories, total_protein_g, total_fat_g, total_carbs_g, total_fiber_g, created_at)
     VALUES (?,?,?,?,?,?,?,?,?,?,?)`,
    [id, uid, payload.name, payload.description ?? null, payload.servings,
     totals.total_calories, totals.total_protein_g, totals.total_fat_g,
     totals.total_carbs_g, totals.total_fiber_g, now]
  );

  for (const ing of payload.ingredients) {
    await db.run(
      `INSERT INTO recipe_ingredients
         (id, recipe_id, fdc_id, food_name, brand_name,
          amount_g, calories, protein_g, fat_g, carbs_g, fiber_g)
       VALUES (?,?,?,?,?,?,?,?,?,?,?)`,
      [uuid(), id,
       ing.fdc_id ?? null, ing.food_name, ing.brand_name ?? null,
       ing.amount_g,
       ing.calories ?? null, ing.protein_g ?? null, ing.fat_g ?? null,
       ing.carbs_g ?? null, ing.fiber_g ?? null]
    );
  }

  return _fetchRecipeWithIngredients(id);
}

export async function apiUpdateRecipe(
  recipeId: string,
  payload: {
    name?:        string;
    description?: string | null;
    servings?:    number;
    ingredients?: RecipeIngredient[];
  }
): Promise<RecipeResponse> {
  const db  = getDb();
  const uid = getCurrentUserId();

  // Verify ownership
  const check = await db.query(
    "SELECT id, servings FROM recipes WHERE id = ? AND user_id = ?",
    [recipeId, uid]
  );
  if (!check.values || check.values.length === 0)
    throw new Error("Recipe not found.");

  const servings = payload.servings ?? check.values[0].servings;

  if (payload.ingredients !== undefined) {
    await db.run("DELETE FROM recipe_ingredients WHERE recipe_id = ?", [recipeId]);
    const totals = _computeTotals(payload.ingredients, servings);

    await db.run(
      `UPDATE recipes SET
         name = COALESCE(?, name),
         description = COALESCE(?, description),
         servings = ?,
         total_calories = ?, total_protein_g = ?, total_fat_g = ?,
         total_carbs_g = ?, total_fiber_g = ?
       WHERE id = ?`,
      [payload.name ?? null, payload.description ?? null, servings,
       totals.total_calories, totals.total_protein_g, totals.total_fat_g,
       totals.total_carbs_g, totals.total_fiber_g, recipeId]
    );

    for (const ing of payload.ingredients) {
      await db.run(
        `INSERT INTO recipe_ingredients
           (id, recipe_id, fdc_id, food_name, brand_name,
            amount_g, calories, protein_g, fat_g, carbs_g, fiber_g)
         VALUES (?,?,?,?,?,?,?,?,?,?,?)`,
        [uuid(), recipeId,
         ing.fdc_id ?? null, ing.food_name, ing.brand_name ?? null,
         ing.amount_g,
         ing.calories ?? null, ing.protein_g ?? null, ing.fat_g ?? null,
         ing.carbs_g ?? null, ing.fiber_g ?? null]
      );
    }
  } else if (payload.name !== undefined || payload.description !== undefined || payload.servings !== undefined) {
    await db.run(
      `UPDATE recipes SET
         name = COALESCE(?, name),
         description = COALESCE(?, description),
         servings = COALESCE(?, servings)
       WHERE id = ?`,
      [payload.name ?? null, payload.description ?? null, payload.servings ?? null, recipeId]
    );
  }

  return _fetchRecipeWithIngredients(recipeId);
}

export async function apiDeleteRecipe(recipeId: string): Promise<void> {
  const db  = getDb();
  const uid = getCurrentUserId();
  await db.run(
    "DELETE FROM recipes WHERE id = ? AND user_id = ?",
    [recipeId, uid]
  );
}

// ── Body measurements ─────────────────────────────────────────────────────────

export interface BodyMeasurement {
  id:           string;
  measured_at:  string;
  weight_kg:    number | null;
  height_cm:    number | null;
  waist_cm:     number | null;
  neck_cm:      number | null;
  hip_cm:       number | null;
  body_fat_pct: number | null;
}

export async function apiListMeasurements(): Promise<BodyMeasurement[]> {
  const db  = getDb();
  const uid = getCurrentUserId();
  const res = await db.query(
    "SELECT * FROM body_measurements WHERE user_id = ? ORDER BY measured_at",
    [uid]
  );
  return res.values ?? [];
}

export async function apiCreateMeasurement(payload: {
  measured_at?: string;
  weight_kg?:   number | null;
  height_cm?:   number | null;
  waist_cm?:    number | null;
  neck_cm?:     number | null;
  hip_cm?:      number | null;
}): Promise<BodyMeasurement> {
  const db   = getDb();
  const uid  = getCurrentUserId();
  const user = await getSession();
  const id   = uuid();
  const date = payload.measured_at ?? new Date().toISOString().slice(0, 10);

  // Compute body fat if we have the required measurements
  let bodyFatPct: number | null = null;
  const height  = payload.height_cm ?? user?.height_cm ?? null;
  const waist   = payload.waist_cm ?? null;
  const neck    = payload.neck_cm ?? null;
  const hip     = payload.hip_cm ?? null;
  const profile = (user?.navy_profile ?? null) as any;

  if (height && waist && neck && profile) {
    try {
      bodyFatPct = Math.round(
        calcBodyFatNavy(height, waist, neck, hip, profile) * 10
      ) / 10;
    } catch { /* ignore */ }
  }

  await db.run(
    `INSERT INTO body_measurements
       (id, user_id, measured_at, weight_kg, height_cm,
        waist_cm, neck_cm, hip_cm, body_fat_pct)
     VALUES (?,?,?,?,?,?,?,?,?)`,
    [id, uid, date,
     payload.weight_kg ?? null, payload.height_cm ?? null,
     payload.waist_cm  ?? null, payload.neck_cm   ?? null,
     payload.hip_cm    ?? null, bodyFatPct]
  );

  return {
    id, measured_at: date,
    weight_kg: payload.weight_kg ?? null,
    height_cm: payload.height_cm ?? null,
    waist_cm:  payload.waist_cm  ?? null,
    neck_cm:   payload.neck_cm   ?? null,
    hip_cm:    payload.hip_cm    ?? null,
    body_fat_pct: bodyFatPct,
  };
}

// ── Workouts ──────────────────────────────────────────────────────────────────

// MET table — same as main.py
export const WORKOUT_METS: Record<string, Record<string, number>> = {
  walking:     { light: 2.5, moderate: 3.5, vigorous: 4.5 },
  running:     { light: 6.0, moderate: 8.0, vigorous: 11.0 },
  cycling:     { light: 4.0, moderate: 6.0, vigorous: 10.0 },
  swimming:    { light: 4.0, moderate: 6.0, vigorous: 8.0 },
  weightlifting:{ light: 3.0, moderate: 5.0, vigorous: 6.0 },
  yoga:        { light: 2.0, moderate: 3.0, vigorous: 4.0 },
  hiit:        { light: 7.0, moderate: 9.0, vigorous: 12.0 },
  elliptical:  { light: 4.0, moderate: 5.5, vigorous: 7.0 },
  rowing:      { light: 4.5, moderate: 6.0, vigorous: 8.5 },
  dancing:     { light: 3.0, moderate: 4.5, vigorous: 6.0 },
  sports:      { light: 4.0, moderate: 6.0, vigorous: 8.0 },
  other:       { light: 3.0, moderate: 5.0, vigorous: 7.0 },
};

function _estimateCalories(
  workoutType: string,
  intensity: string,
  durationMin: number,
  weightKg: number
): number {
  const mets = WORKOUT_METS[workoutType.toLowerCase()] ?? WORKOUT_METS.other;
  const met  = mets[intensity] ?? mets.moderate ?? 5.0;
  return Math.round(met * weightKg * (durationMin / 60) * 10) / 10;
}

export interface WorkoutEntry {
  id:              string;
  log_date:        string;
  logged_at:       string;
  name:            string | null;
  workout_type:    string | null;
  duration_min:    number | null;
  intensity:       string | null;
  calories_burned: number;
  source:          string;
  notes:           string | null;
}

export async function apiListWorkouts(logDate: string): Promise<WorkoutEntry[]> {
  const db  = getDb();
  const uid = getCurrentUserId();
  const res = await db.query(
    "SELECT * FROM workout_logs WHERE user_id = ? AND log_date = ? ORDER BY logged_at",
    [uid, logDate]
  );
  return res.values ?? [];
}

export async function apiCreateWorkout(payload: Record<string, any> & {
  source:        string;
  name?:         string | null;
  workout_type?: string | null;
  duration_min?: number | null;
  intensity?:    string | null;
  calories_burned?: number | null;
  notes?:        string | null;
  log_date?:     string | null;
}): Promise<WorkoutEntry> {
  const db   = getDb();
  const uid  = getCurrentUserId();
  const user = await getSession();
  const id   = uuid();
  const now  = new Date().toISOString();
  const date = payload.log_date ?? now.slice(0, 10);

  let calories = payload.calories_burned ?? 0;

  if (payload.source === "estimated") {
    if (!payload.workout_type || !payload.duration_min || !payload.intensity) {
      throw new Error("workout_type, duration_min, and intensity are required for estimated workouts.");
    }
    // Resolve weight from most recent measurement
    let weightKg = user?.weight_kg ?? 70.0;
    const mRes = await db.query(
      `SELECT weight_kg FROM body_measurements
       WHERE user_id = ? AND weight_kg IS NOT NULL
       ORDER BY measured_at DESC LIMIT 1`,
      [uid]
    );
    if (mRes.values && mRes.values.length > 0) {
      weightKg = mRes.values[0].weight_kg;
    }
    calories = _estimateCalories(
      payload.workout_type, payload.intensity, payload.duration_min, weightKg
    );
  }

  await db.run(
    `INSERT INTO workout_logs
       (id, user_id, log_date, logged_at, name, workout_type,
        duration_min, intensity, calories_burned, source, notes)
     VALUES (?,?,?,?,?,?,?,?,?,?,?)`,
    [id, uid, date, now,
     payload.name ?? null, payload.workout_type ?? null,
     payload.duration_min ?? null, payload.intensity ?? null,
     calories, payload.source, payload.notes ?? null]
  );

  return {
    id, log_date: date, logged_at: now,
    name:            payload.name ?? null,
    workout_type:    payload.workout_type ?? null,
    duration_min:    payload.duration_min ?? null,
    intensity:       payload.intensity ?? null,
    calories_burned: calories,
    source:          payload.source,
    notes:           payload.notes ?? null,
  };
}

export async function apiDeleteWorkout(workoutId: string): Promise<void> {
  const db  = getDb();
  const uid = getCurrentUserId();
  await db.run(
    "DELETE FROM workout_logs WHERE id = ? AND user_id = ?",
    [workoutId, uid]
  );
}

// ── User profile update (for Dashboard settings) ──────────────────────────────

export async function apiUpdateMe(patch: any): Promise<UserProfile> {
  return updateUserProfile(patch);
}

// ── Settings: password change, data export, account delete ───────────────────

export async function apiChangePassword(newPassword: string): Promise<void> {
  const { changePassword } = await import("./auth");
  await changePassword(newPassword);
}

export async function apiDeleteAccount(): Promise<void> {
  const db  = getDb();
  const uid = getCurrentUserId();
  await db.run("DELETE FROM users WHERE id = ?", [uid]);
  localStorage.clear();
}

export async function apiExportData(): Promise<object> {
  const db  = getDb();
  const uid = getCurrentUserId();
  const [user, logs, recipes, ingredients, measurements, workouts] = await Promise.all([
    db.query("SELECT * FROM users WHERE id = ?", [uid]),
    db.query("SELECT * FROM food_logs WHERE user_id = ?", [uid]),
    db.query("SELECT * FROM recipes WHERE user_id = ?", [uid]),
    db.query("SELECT ri.* FROM recipe_ingredients ri JOIN recipes r ON ri.recipe_id = r.id WHERE r.user_id = ?", [uid]),
    db.query("SELECT * FROM body_measurements WHERE user_id = ?", [uid]),
    db.query("SELECT * FROM workout_logs WHERE user_id = ?", [uid]),
  ]);
  const u = { ...(user.values?.[0] ?? {}) };
  delete u.hashed_password;
  return {
    exported_at: new Date().toISOString(),
    user: u,
    food_logs: logs.values ?? [],
    recipes: recipes.values ?? [],
    recipe_ingredients: ingredients.values ?? [],
    body_measurements: measurements.values ?? [],
    workout_logs: workouts.values ?? [],
  };
}
