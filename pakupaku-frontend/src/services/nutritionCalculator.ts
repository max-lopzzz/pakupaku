/**
 * nutritionCalculator.ts
 * ──────────────────────────────────────────────────────
 * TypeScript port of nutrition_calculator.py.
 * All formulas, constants, and logic are identical to the Python version.
 */

// ── Constants ─────────────────────────────────────────────────────────────────

export const ACTIVITY_FACTORS: Record<string, number> = {
  sedentary:   1.200,
  light:       1.375,
  moderate:    1.550,
  very_active: 1.725,
  extreme:     1.900,
};

const PROTEIN_PER_KG: Record<string, number> = {
  lose:     2.2,
  maintain: 1.8,
  gain:     2.0,
};

const KCAL_PER_KG_FAT  = 7700;
const KCAL_PER_KG_LEAN = 4500;
const MAX_DEFICIT      = -1000;
const MAX_SURPLUS      = 500;

// ── Metabolic conditions ──────────────────────────────────────────────────────

interface MetabolicCondition {
  name:             string;
  bmr_multiplier:   number | null;
  note:             string;
  requires_consult: boolean;
}

export const CONDITIONS: Record<string, MetabolicCondition> = {
  hypothyroidism_untreated: {
    name: "Hypothyroidism (untreated)",
    bmr_multiplier: 0.75,
    note: "BMR estimate reduced by ~25% (conservative midpoint of 15-40% range). Actual impact varies widely -- consult your endocrinologist before making dietary changes.",
    requires_consult: true,
  },
  hypothyroidism_treated: {
    name: "Hypothyroidism (treated/medicated)",
    bmr_multiplier: null,
    note: "If your levels are well-controlled on medication, BMR is likely normal. No adjustment applied.",
    requires_consult: false,
  },
  hyperthyroidism_untreated: {
    name: "Hyperthyroidism (untreated)",
    bmr_multiplier: 1.40,
    note: "BMR estimate increased by ~40% (midpoint of 25-80% range). This range is extremely wide -- do not use for weight loss planning without medical guidance.",
    requires_consult: true,
  },
  hyperthyroidism_treated: {
    name: "Hyperthyroidism (treated/medicated)",
    bmr_multiplier: null,
    note: "If your levels are well-controlled on medication, BMR is likely normal. No adjustment applied.",
    requires_consult: false,
  },
  hiv_wasting: {
    name: "HIV/AIDS with wasting syndrome",
    bmr_multiplier: 1.20,
    note: "Increased energy needs (~20%) estimated due to immune activation and wasting. A registered dietitian familiar with HIV care is strongly recommended.",
    requires_consult: true,
  },
  cancer_active: {
    name: "Cancer (active)",
    bmr_multiplier: 1.20,
    note: "Hypermetabolic state estimated at ~20% increase. Varies by cancer type, stage, and treatment. An oncology dietitian is required for accurate planning.",
    requires_consult: true,
  },
  pcos: {
    name: "PCOS",
    bmr_multiplier: null,
    note: "PCOS primarily affects insulin sensitivity and fat distribution, not raw BMR. No BMR multiplier applied. Lower-GI carbohydrate distribution is often more effective than calorie cuts alone -- consult a dietitian familiar with PCOS.",
    requires_consult: true,
  },
  cushings: {
    name: "Cushing's Syndrome",
    bmr_multiplier: null,
    note: "Cushing's drives cortisol-mediated fat storage, making standard calorie math unreliable. No adjustment applied. Endocrinology and dietitian involvement is required.",
    requires_consult: true,
  },
  diabetes_t1: {
    name: "Type 1 Diabetes",
    bmr_multiplier: null,
    note: "Energy partitioning is affected by insulin management. Macro ratios and meal timing matter more than total calories alone. Work with a diabetes-specialist dietitian.",
    requires_consult: true,
  },
  eating_disorder_history: {
    name: "Eating Disorder History",
    bmr_multiplier: null,
    note: "BMR may be suppressed due to restriction history. Aggressive caloric deficits are contraindicated. Please work with a clinical dietitian before pursuing weight loss goals.",
    requires_consult: true,
  },
};

// ── HRT helpers ───────────────────────────────────────────────────────────────

function _hrtT(hrtMonths: number, hrtType: string): number {
  if (hrtType === "estrogen")     return Math.min(hrtMonths / 24.0, 1.0);
  if (hrtType === "testosterone") return Math.min(hrtMonths / 12.0, 1.0);
  return 0.0;
}

export function hrtNavyBlendT(
  hrtType: string,
  hrtMonths: number
): number {
  const t = _hrtT(hrtMonths, hrtType);
  if (hrtType === "estrogen")     return t;
  if (hrtType === "testosterone") return 1.0 - t;
  return 0.5;
}

export function interpolateBmrHrt(
  weightKg: number,
  heightCm: number,
  age: number,
  hrtType: string,
  hrtMonths: number,
  bodyFatPct: number
): number {
  const bmrMale   = 10 * weightKg + 6.25 * heightCm - 5 * age + 5;
  const bmrFemale = 10 * weightKg + 6.25 * heightCm - 5 * age - 161;
  const lbm       = weightKg * (1 - bodyFatPct / 100);
  const bmrKatch  = 370 + 21.6 * lbm;
  const t         = _hrtT(hrtMonths, hrtType);

  if (hrtType === "estrogen") {
    if (t <= 0.5) {
      const s = t / 0.5;
      return (1 - s) * bmrMale + s * bmrKatch;
    } else {
      const s = (t - 0.5) / 0.5;
      return (1 - s) * bmrKatch + s * bmrFemale;
    }
  } else if (hrtType === "testosterone") {
    if (t <= 0.5) {
      const s = t / 0.5;
      return (1 - s) * bmrFemale + s * bmrKatch;
    } else {
      const s = (t - 0.5) / 0.5;
      return (1 - s) * bmrKatch + s * bmrMale;
    }
  }
  return bmrKatch;
}

// ── Body fat % (U.S. Navy method) ─────────────────────────────────────────────

export function calcBodyFatNavy(
  heightCm: number,
  waistCm:  number,
  neckCm:   number,
  hipCm:    number | null,
  profile:  "male" | "female" | "average" | "blend",
  hrtBlendT?: number | null
): number {
  // The US Navy formula constants are calibrated for measurements in INCHES.
  const CM_TO_IN = 0.393701;
  const h  = heightCm * CM_TO_IN;
  const w  = waistCm  * CM_TO_IN;
  const n  = neckCm   * CM_TO_IN;
  const hp = hipCm != null ? hipCm * CM_TO_IN : null;

  const _male   = () => 86.010  * Math.log10(w - n)           - 70.041 * Math.log10(h) + 36.76;
  const _female = () => 163.205 * Math.log10(w + hp! - n) - 97.684 * Math.log10(h) - 78.387;

  if (profile === "male") return _male();

  if (profile === "female") {
    if (hp === null || hp === undefined)
      throw new Error("hip_cm is required for the female Navy formula.");
    return _female();
  }

  if (profile === "average" || profile === "blend") {
    if (hp === null || hp === undefined)
      throw new Error("hip_cm is required for blended Navy formulas.");
    const t = (profile === "blend" && hrtBlendT != null) ? hrtBlendT : 0.5;
    return (1 - t) * _male() + t * _female();
  }

  throw new Error(`Unknown profile '${profile}'.`);
}

// ── Body fat % (BMI-based estimation - Deurenberg formula) ──────────────────────

export function calcBodyFatBmi(
  bmi:     number,
  age:     number,
  profile: string
): number {
  // Deurenberg et al. (1991) BMI-based body fat estimation formula
  // For adults: BF% = 1.20 × BMI + 0.23 × Age - (10.8 × sex) - 5.4
  // where sex = 0 for women, 1 for men
  // This formula explains ~79% of variance in body fat percentage
  
  let sex: number;
  if (profile === "male" || profile === "katch") {
    sex = 1; // male
  } else if (profile === "female") {
    sex = 0; // female
  } else if (profile === "average" || profile === "hrt") {
    // For average/blend profiles, use average of male and female
    const maleBf = 1.20 * bmi + 0.23 * age - 10.8 * 1 - 5.4;
    const femaleBf = 1.20 * bmi + 0.23 * age - 10.8 * 0 - 5.4;
    return (maleBf + femaleBf) / 2;
  } else {
    sex = 0.5; // default to average
  }
  
  const bodyFatPct = 1.20 * bmi + 0.23 * age - 10.8 * sex - 5.4;
  // Clamp to reasonable range (0-60%)
  return Math.max(0, Math.min(60, bodyFatPct));
}

// ── BMR ───────────────────────────────────────────────────────────────────────

export function calcBmr(
  weightKg:   number,
  heightCm:   number,
  age:        number,
  profile:    string,
  bodyFatPct?: number | null
): number {
  const _male   = () => 10 * weightKg + 6.25 * heightCm - 5 * age + 5;
  const _female = () => 10 * weightKg + 6.25 * heightCm - 5 * age - 161;

  if (profile === "male")    return _male();
  if (profile === "female")  return _female();
  if (profile === "average") return (_male() + _female()) / 2;
  if (profile === "katch") {
    if (bodyFatPct == null)
      throw new Error("body_fat_pct is required for Katch-McArdle.");
    const lbm = weightKg * (1 - bodyFatPct / 100);
    return 370 + 21.6 * lbm;
  }
  throw new Error(`Unknown profile '${profile}'.`);
}

// ── Metabolic condition adjustment ────────────────────────────────────────────

interface ConditionNote {
  condition:          string;
  multiplier_applied: number | null;
  note:               string;
}

interface ConditionResult {
  adjusted_bmr:     number;
  condition_notes:  ConditionNote[];
  requires_consult: boolean;
}

export function applyMetabolicConditions(
  bmr:            number,
  conditionKeys:  string[]
): ConditionResult {
  let adjustedBmr    = bmr;
  const notes:       ConditionNote[] = [];
  let requiresConsult = false;

  for (const key of conditionKeys) {
    const cond = CONDITIONS[key];
    if (!cond) {
      notes.push({ condition: key, multiplier_applied: null, note: `Unknown condition key '${key}' -- skipped.` });
      continue;
    }
    if (cond.bmr_multiplier !== null) adjustedBmr *= cond.bmr_multiplier;
    if (cond.requires_consult)        requiresConsult = true;
    notes.push({ condition: cond.name, multiplier_applied: cond.bmr_multiplier, note: cond.note });
  }

  return { adjusted_bmr: Math.round(adjustedBmr), condition_notes: notes, requires_consult: requiresConsult };
}

// ── TDEE ──────────────────────────────────────────────────────────────────────

export function calcTdee(bmr: number, activityLevel: string): number {
  const factor = ACTIVITY_FACTORS[activityLevel];
  if (factor == null) throw new Error(`Unknown activity level '${activityLevel}'.`);
  return bmr * factor;
}

// ── Goal adjustment ───────────────────────────────────────────────────────────

export function calcGoalAdjustment(
  goal: string,
  paceKgPerWeek: number
): [number, string] {
  if (goal === "maintain") return [0, ""];

  let warning = "";

  if (goal === "lose") {
    let raw = -(paceKgPerWeek * KCAL_PER_KG_FAT / 7);
    if (raw < MAX_DEFICIT) {
      warning = `Your requested pace requires a ${Math.abs(raw).toFixed(0)} kcal/day deficit, which exceeds the safe ceiling of ${Math.abs(MAX_DEFICIT)} kcal/day. The deficit has been capped to protect lean muscle mass.`;
      raw = MAX_DEFICIT;
    }
    return [raw, warning];
  }

  if (goal === "gain") {
    let raw = paceKgPerWeek * KCAL_PER_KG_LEAN / 7;
    if (raw > MAX_SURPLUS) {
      warning = `Your requested pace requires a ${raw.toFixed(0)} kcal/day surplus, which exceeds the recommended ceiling of ${MAX_SURPLUS} kcal/day. The surplus has been capped.`;
      raw = MAX_SURPLUS;
    }
    return [raw, warning];
  }

  return [0, ""];
}

// ── Macros ────────────────────────────────────────────────────────────────────

export function calcMacros(
  totalKcal:  number,
  weightKg:   number,
  bodyFatPct: number,
  goal:       string
): { protein_g: number; fat_g: number; carbs_g: number } {
  const proteinPerKg = PROTEIN_PER_KG[goal];
  if (proteinPerKg == null) throw new Error(`Unknown goal '${goal}'.`);

  const lbm      = weightKg * (1 - bodyFatPct / 100);
  const proteinG = lbm * proteinPerKg;
  const fatG     = Math.max(weightKg * 0.5, (totalKcal * 0.25) / 9);
  const carbKcal = totalKcal - proteinG * 4 - fatG * 9;
  const carbG    = Math.max(carbKcal / 4, 0);

  return {
    protein_g: Math.round(proteinG),
    fat_g:     Math.round(fatG),
    carbs_g:   Math.round(carbG),
  };
}
