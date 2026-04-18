"""
nutrition_calculator.py
-----------------------
Calculates body fat %, BMR, TDEE, and macros.

Features:
  - Custom goals bypass (for users who've already seen a dietitian)
  - Inclusive hormonal profiles with continuous HRT-duration interpolation
  - Separate body-shape question for the Navy body fat formula
  - Pace-of-change selector for lose/gain goals
  - Metabolic condition adjustments with clinical safety flags
"""

import math
from dataclasses import dataclass
from typing import Optional, Dict, List, Tuple


# ─────────────────────────────────────────────
#  CONSTANTS
# ─────────────────────────────────────────────

ACTIVITY_FACTORS = {
    "sedentary":   1.200,   # desk job, little/no exercise
    "light":       1.375,   # 1–3 days/week
    "moderate":    1.550,   # 3–5 days/week
    "very_active": 1.725,   # 6–7 days/week
    "extreme":     1.900,   # physical job + daily training
}

PROTEIN_PER_KG = {
    "lose":     2.2,
    "maintain": 1.8,
    "gain":     2.0,
}

# kcal per kg of body tissue
# Fat loss:    ~7,700 kcal deficit  = 1 kg fat lost
# Muscle gain: ~4,500 kcal surplus  = 1 kg lean gained (conservative)
KCAL_PER_KG_FAT  = 7_700
KCAL_PER_KG_LEAN = 4_500

# Hard safety limits (kcal/day adjustment from TDEE)
MAX_DEFICIT = -1_000   # beyond this, lean mass loss accelerates sharply
MAX_SURPLUS =   +500   # beyond this, excess fat gain outpaces lean gain


# ─────────────────────────────────────────────
#  METABOLIC CONDITIONS
# ─────────────────────────────────────────────

@dataclass
class MetabolicCondition:
    name: str
    bmr_multiplier: Optional[float]  # None = flag only, do not adjust
    note: str
    requires_consult: bool


CONDITIONS: Dict[str, MetabolicCondition] = {
    "hypothyroidism_untreated": MetabolicCondition(
        name="Hypothyroidism (untreated)",
        bmr_multiplier=0.75,
        note=(
            "BMR estimate reduced by ~25% (conservative midpoint of 15-40% range). "
            "Actual impact varies widely -- consult your endocrinologist before "
            "making dietary changes."
        ),
        requires_consult=True,
    ),
    "hypothyroidism_treated": MetabolicCondition(
        name="Hypothyroidism (treated/medicated)",
        bmr_multiplier=None,
        note=(
            "If your levels are well-controlled on medication, BMR is likely "
            "normal. No adjustment applied."
        ),
        requires_consult=False,
    ),
    "hyperthyroidism_untreated": MetabolicCondition(
        name="Hyperthyroidism (untreated)",
        bmr_multiplier=1.40,
        note=(
            "BMR estimate increased by ~40% (midpoint of 25-80% range). "
            "This range is extremely wide -- do not use for weight loss planning "
            "without medical guidance."
        ),
        requires_consult=True,
    ),
    "hyperthyroidism_treated": MetabolicCondition(
        name="Hyperthyroidism (treated/medicated)",
        bmr_multiplier=None,
        note=(
            "If your levels are well-controlled on medication, BMR is likely "
            "normal. No adjustment applied."
        ),
        requires_consult=False,
    ),
    "hiv_wasting": MetabolicCondition(
        name="HIV/AIDS with wasting syndrome",
        bmr_multiplier=1.20,
        note=(
            "Increased energy needs (~20%) estimated due to immune activation "
            "and wasting. A registered dietitian familiar with HIV care is "
            "strongly recommended."
        ),
        requires_consult=True,
    ),
    "cancer_active": MetabolicCondition(
        name="Cancer (active)",
        bmr_multiplier=1.20,
        note=(
            "Hypermetabolic state estimated at ~20% increase. Varies by cancer "
            "type, stage, and treatment. An oncology dietitian is required for "
            "accurate planning."
        ),
        requires_consult=True,
    ),
    "pcos": MetabolicCondition(
        name="PCOS",
        bmr_multiplier=None,
        note=(
            "PCOS primarily affects insulin sensitivity and fat distribution, "
            "not raw BMR. No BMR multiplier applied. Lower-GI carbohydrate "
            "distribution is often more effective than calorie cuts alone -- "
            "consult a dietitian familiar with PCOS."
        ),
        requires_consult=True,
    ),
    "cushings": MetabolicCondition(
        name="Cushing's Syndrome",
        bmr_multiplier=None,
        note=(
            "Cushing's drives cortisol-mediated fat storage, making standard "
            "calorie math unreliable. No adjustment applied. Endocrinology "
            "and dietitian involvement is required."
        ),
        requires_consult=True,
    ),
    "diabetes_t1": MetabolicCondition(
        name="Type 1 Diabetes",
        bmr_multiplier=None,
        note=(
            "Energy partitioning is affected by insulin management. Macro "
            "ratios and meal timing matter more than total calories alone. "
            "Work with a diabetes-specialist dietitian."
        ),
        requires_consult=True,
    ),
    "eating_disorder_history": MetabolicCondition(
        name="Eating Disorder History",
        bmr_multiplier=None,
        note=(
            "BMR may be suppressed due to restriction history. Aggressive "
            "caloric deficits are contraindicated. Please work with a clinical "
            "dietitian before pursuing weight loss goals."
        ),
        requires_consult=True,
    ),
    "fibromyalgia": MetabolicCondition(
        name="Fibromyalgia",
        bmr_multiplier=None,
        note=(
            "Fibromyalgia's effect on resting metabolism is not well established. "
            "No BMR adjustment applied. Fatigue and pain may significantly reduce "
            "activity tolerance -- calorie targets may need downward adjustment. "
            "An anti-inflammatory dietary pattern is often recommended; consult "
            "a dietitian familiar with chronic pain conditions."
        ),
        requires_consult=True,
    ),
}


# ─────────────────────────────────────────────
#  HRT INTERPOLATION HELPERS
# ─────────────────────────────────────────────

def _hrt_t(hrt_months: int, hrt_type: str) -> float:
    """
    Returns a blend factor t in [0.0, 1.0] representing how far along
    the HRT-driven body composition shift is.

    Estrogen (MTF):     t ramps 0.0 -> 1.0 over 0-24 months.
    Testosterone (FTM): t ramps 0.0 -> 1.0 over 0-12 months (T acts faster).

    t=0.0 means composition still matches pre-HRT physiology.
    t=1.0 means composition has largely converged to target physiology.
    """
    if hrt_type == "estrogen":
        return min(hrt_months / 24.0, 1.0)
    elif hrt_type == "testosterone":
        return min(hrt_months / 12.0, 1.0)
    return 0.0


def interpolate_bmr_hrt(
    weight_kg: float,
    height_cm: float,
    age: int,
    hrt_type: str,
    hrt_months: int,
    body_fat_pct: float,
) -> float:
    """
    Smoothly interpolate BMR between male and female Mifflin-St Jeor
    based on HRT duration, routing through Katch-McArdle at the midpoint
    for a physiologically smoother curve.

    Estrogen (MTF):     male formula -> katch -> female formula
    Testosterone (FTM): female formula -> katch -> male formula
    """
    bmr_male   = (10 * weight_kg) + (6.25 * height_cm) - (5 * age) + 5
    bmr_female = (10 * weight_kg) + (6.25 * height_cm) - (5 * age) - 161
    lbm        = weight_kg * (1 - body_fat_pct / 100)
    bmr_katch  = 370 + (21.6 * lbm)

    t = _hrt_t(hrt_months, hrt_type)

    if hrt_type == "estrogen":
        if t <= 0.5:
            s = t / 0.5
            return (1 - s) * bmr_male + s * bmr_katch
        else:
            s = (t - 0.5) / 0.5
            return (1 - s) * bmr_katch + s * bmr_female

    elif hrt_type == "testosterone":
        if t <= 0.5:
            s = t / 0.5
            return (1 - s) * bmr_female + s * bmr_katch
        else:
            s = (t - 0.5) / 0.5
            return (1 - s) * bmr_katch + s * bmr_male

    return bmr_katch


def hrt_navy_blend_t(hrt_type: str, hrt_months: int) -> float:
    """
    Returns a body-fat formula blend weight in [0.0, 1.0] based on HRT duration.
    0.0 = 100% male Navy formula
    1.0 = 100% female Navy formula

    Estrogen: starts at 0.0, reaches 1.0 at 24 months.
    Testosterone: starts at 1.0, reaches 0.0 at 12 months.
    """
    t = _hrt_t(hrt_months, hrt_type)
    if hrt_type == "estrogen":
        return t           # 0.0 (male) -> 1.0 (female)
    elif hrt_type == "testosterone":
        return 1.0 - t     # 1.0 (female) -> 0.0 (male)
    return 0.5


# ─────────────────────────────────────────────
#  BODY FAT %  (U.S. Navy Method)
# ─────────────────────────────────────────────

def calc_body_fat_navy(
    height_cm: float,
    waist_cm: float,
    neck_cm: float,
    hip_cm: Optional[float] = None,
    profile: str = "female",
    hrt_blend_t: Optional[float] = None,
) -> float:
    """
    Estimate body fat % using the U.S. Navy tape-measure method.

    profile options:
        "male"    -- male formula only
        "female"  -- female formula only (requires hip_cm)
        "average" -- 50/50 blend (requires hip_cm)
        "blend"   -- weighted blend by hrt_blend_t (requires hip_cm)
                     0.0 = 100% male, 1.0 = 100% female
    """
    def _male(h, w, n):
        return 86.010 * math.log10(w - n) - 70.041 * math.log10(h) + 36.76

    def _female(h, w, n, hip):
        return 163.205 * math.log10(w + hip - n) - 97.684 * math.log10(h) - 78.387

    if profile == "male":
        return _male(height_cm, waist_cm, neck_cm)

    elif profile == "female":
        if hip_cm is None:
            raise ValueError("hip_cm is required for the female Navy formula.")
        return _female(height_cm, waist_cm, neck_cm, hip_cm)

    elif profile in ("average", "blend"):
        if hip_cm is None:
            raise ValueError("hip_cm is required for blended Navy formulas.")
        m = _male(height_cm, waist_cm, neck_cm)
        f = _female(height_cm, waist_cm, neck_cm, hip_cm)
        t = hrt_blend_t if (profile == "blend" and hrt_blend_t is not None) else 0.5
        return (1 - t) * m + t * f

    else:
        raise ValueError(
            f"Unknown profile '{profile}'. Use 'male', 'female', 'average', or 'blend'."
        )


# ─────────────────────────────────────────────
#  BMR  (non-HRT paths)
# ─────────────────────────────────────────────

def calc_bmr(
    weight_kg: float,
    height_cm: float,
    age: int,
    profile: str = "katch",
    body_fat_pct: Optional[float] = None,
) -> float:
    """
    Calculate BMR for non-HRT or fully-transitioned users.

    profile options:
        "male"    -- Mifflin-St Jeor male
        "female"  -- Mifflin-St Jeor female
        "average" -- average of both
        "katch"   -- Katch-McArdle, sex-neutral (requires body_fat_pct)
    """
    def _male(w, h, a):
        return (10 * w) + (6.25 * h) - (5 * a) + 5

    def _female(w, h, a):
        return (10 * w) + (6.25 * h) - (5 * a) - 161

    if profile == "male":
        return _male(weight_kg, height_cm, age)
    elif profile == "female":
        return _female(weight_kg, height_cm, age)
    elif profile == "average":
        return (_male(weight_kg, height_cm, age) + _female(weight_kg, height_cm, age)) / 2
    elif profile == "katch":
        if body_fat_pct is None:
            raise ValueError("body_fat_pct is required for Katch-McArdle.")
        lbm = weight_kg * (1 - body_fat_pct / 100)
        return 370 + (21.6 * lbm)
    else:
        raise ValueError(
            f"Unknown profile '{profile}'. Use 'male', 'female', 'average', or 'katch'."
        )


# ─────────────────────────────────────────────
#  METABOLIC CONDITION ADJUSTMENT
# ─────────────────────────────────────────────

def apply_metabolic_conditions(bmr: float, condition_keys: List[str]) -> Dict:
    """
    Apply metabolic condition adjustments to a base BMR.
    Multiplier-eligible conditions stack sequentially.
    Flag-only conditions are noted without changing the number.
    """
    adjusted_bmr     = bmr
    condition_notes  = []
    requires_consult = False

    for key in condition_keys:
        condition = CONDITIONS.get(key)
        if condition is None:
            condition_notes.append({
                "condition": key,
                "multiplier_applied": None,
                "note": f"Unknown condition key '{key}' -- skipped.",
            })
            continue

        if condition.bmr_multiplier is not None:
            adjusted_bmr *= condition.bmr_multiplier

        if condition.requires_consult:
            requires_consult = True

        condition_notes.append({
            "condition": condition.name,
            "multiplier_applied": condition.bmr_multiplier,
            "note": condition.note,
        })

    return {
        "adjusted_bmr":     round(adjusted_bmr),
        "condition_notes":  condition_notes,
        "requires_consult": requires_consult,
    }


# ─────────────────────────────────────────────
#  TDEE
# ─────────────────────────────────────────────

def calc_tdee(bmr: float, activity_level: str) -> float:
    """Calculate TDEE from BMR and activity level (no goal adjustment)."""
    if activity_level not in ACTIVITY_FACTORS:
        raise ValueError(f"Unknown activity level '{activity_level}'.")
    return bmr * ACTIVITY_FACTORS[activity_level]


# ─────────────────────────────────────────────
#  GOAL ADJUSTMENT (pace-based)
# ─────────────────────────────────────────────

def calc_goal_adjustment(
    goal: str,
    pace_kg_per_week: float,
) -> Tuple[float, str]:
    """
    Convert a desired pace (kg/week) into a daily kcal adjustment.

    lose:     deficit = pace x 7700 / 7  (kcal per day from fat tissue)
    gain:     surplus = pace x 4500 / 7  (kcal per day, conservative lean estimate)
    maintain: always 0

    Returns (kcal_adjustment, warning_or_empty).
    Adjustment is clamped to safety limits with a warning if exceeded.
    """
    if goal == "maintain":
        return 0.0, ""

    warning = ""

    if goal == "lose":
        raw = -(pace_kg_per_week * KCAL_PER_KG_FAT / 7)
        if raw < MAX_DEFICIT:
            warning = (
                f"Your requested pace requires a {abs(raw):.0f} kcal/day deficit, "
                f"which exceeds the safe ceiling of {abs(MAX_DEFICIT)} kcal/day. "
                f"The deficit has been capped to protect lean muscle mass."
            )
            raw = MAX_DEFICIT
        return raw, warning

    if goal == "gain":
        raw = pace_kg_per_week * KCAL_PER_KG_LEAN / 7
        if raw > MAX_SURPLUS:
            warning = (
                f"Your requested pace requires a {raw:.0f} kcal/day surplus, "
                f"which exceeds the recommended ceiling of {MAX_SURPLUS} kcal/day. "
                f"Excess calories above this tend to add fat rather than lean mass. "
                f"The surplus has been capped."
            )
            raw = MAX_SURPLUS
        return raw, warning

    return 0.0, ""


# ─────────────────────────────────────────────
#  MACROS
# ─────────────────────────────────────────────

def calc_macros(
    total_kcal: float,
    weight_kg: float,
    body_fat_pct: float,
    goal: str,
) -> dict:
    """
    Calculate macro targets from total calories using lean body mass for protein.
    Fat floor: max(0.5 g/kg bodyweight, 25% of total kcal / 9).
    Carbs fill remaining calories (floored at 0).
    """
    if goal not in PROTEIN_PER_KG:
        raise ValueError(f"Unknown goal '{goal}'.")

    lbm       = weight_kg * (1 - body_fat_pct / 100)
    protein_g = lbm * PROTEIN_PER_KG[goal]
    fat_g     = max(weight_kg * 0.5, total_kcal * 0.25 / 9)

    carb_kcal = total_kcal - (protein_g * 4) - (fat_g * 9)
    carb_g    = max(carb_kcal / 4, 0)

    return {
        "protein_g": round(protein_g),
        "fat_g":     round(fat_g),
        "carbs_g":   round(carb_g),
    }


# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────

def _wrap(text: str, width: int = 52, indent: str = "  ") -> str:
    """Word-wrap a string, returning indented lines as a single string."""
    words = text.split()
    lines = []
    line  = indent
    for word in words:
        if len(line) + len(word) + 1 > width:
            lines.append(line.rstrip())
            line = indent + "  " + word + " "
        else:
            line += word + " "
    if line.strip():
        lines.append(line.rstrip())
    return "\n".join(lines)


# ─────────────────────────────────────────────
#  MAIN ENTRY POINT
# ─────────────────────────────────────────────

def run_calculator():
    print("\n" + "=" * 55)
    print("  NUTRITION CALCULATOR")
    print("=" * 55)

    # ── Custom goals bypass ───────────────────────────────────
    print("\nHave you already received calorie and macro goals")
    print("from a dietitian or other medical professional?")
    use_custom = input(
        "Enter 'yes' to input your own goals, or press Enter to calculate: "
    ).strip().lower()

    if use_custom == "yes":
        print("\n── Custom Goals ─────────────────────────────────────")
        try:
            custom_kcal    = float(input("  Daily calorie goal (kcal): "))
            custom_protein = float(input("  Daily protein goal (g): "))
            custom_fat     = float(input("  Daily fat goal (g): "))
            custom_carbs   = float(input("  Daily carbohydrate goal (g): "))
        except ValueError:
            print("\n  Invalid input. Please enter numbers only.")
            return

        print("\n" + "=" * 55)
        print("  YOUR CUSTOM GOALS (from your dietitian)")
        print("=" * 55)
        print(f"  Calories  : {custom_kcal:.0f} kcal/day")
        print(f"  Protein   : {custom_protein:.0f} g/day")
        print(f"  Fat       : {custom_fat:.0f} g/day")
        print(f"  Carbs     : {custom_carbs:.0f} g/day")
        print("=" * 55)
        print("\n  These goals have been recorded as-is.")
        print("  Follow your professional's guidance over any")
        print("  calculated estimates.\n")
        return

    # ── Biometrics ────────────────────────────────────────────
    print("\n── Biometrics ───────────────────────────────────────")
    try:
        weight_kg = float(input("  Weight (kg): "))
        height_cm = float(input("  Height (cm): "))
        age       = int(input("  Age (years): "))
    except ValueError:
        print("\n  Invalid input. Please enter numbers only.")
        return

    # ── Hormonal profile ──────────────────────────────────────
    print("\n── Hormonal Profile ─────────────────────────────────")
    print("  Used to select the most accurate BMR formula.")
    print("  Separate from your gender identity.")
    print()
    print("  1 -- Male physiology")
    print("       (cis male, or trans male fully transitioned / 1+ yr on T)")
    print("  2 -- Female physiology")
    print("       (cis female, or trans female fully transitioned / 2+ yr on E)")
    print("  3 -- Currently on estrogen HRT (MTF / non-binary)")
    print("  4 -- Currently on testosterone HRT (FTM / non-binary)")
    print("  5 -- Not on HRT, Katch-McArdle (sex-neutral, uses lean body mass)")
    print("  6 -- Unsure / prefer not to say  -> defaults to Katch-McArdle")

    profile_choice   = input("\n  Enter choice (1-6): ").strip()
    hrt_type         = None
    hrt_months       = 0
    hormonal_profile = "katch"

    if profile_choice == "1":
        hormonal_profile = "male"
    elif profile_choice == "2":
        hormonal_profile = "female"
    elif profile_choice in ("3", "4"):
        hrt_type         = "estrogen" if profile_choice == "3" else "testosterone"
        hormonal_profile = "hrt"
        label            = "estrogen" if hrt_type == "estrogen" else "testosterone"
        try:
            hrt_months = int(input(f"  Months on {label} HRT: "))
        except ValueError:
            print("  Invalid input -- defaulting to 0 months.")
            hrt_months = 0
    # choices 5 and 6 both default to katch (already set above)

    # ── Body shape (Navy formula) ─────────────────────────────
    print("\n── Body Shape (for body fat % formula) ─────────────")
    print("  Pick whichever matches your current body.")
    print("  Independent of gender identity or hormonal profile.")
    print()
    print("  1 -- Stores fat mainly around the waist")
    print("       (android/apple shape -- hip not needed)")
    print("  2 -- Stores fat around hips/thighs as well as waist")
    print("       (gynoid/pear shape -- hip measurement needed)")
    print("  3 -- Currently transitioning -- let HRT months decide the blend")
    print("       (hip measurement needed)")
    print("  4 -- Unsure -- enter hip measurement, use 50/50 blend")

    shape_choice = input("\n  Enter choice (1-4): ").strip()
    navy_profile = "female"
    navy_blend_t = None

    if shape_choice == "1":
        navy_profile = "male"
    elif shape_choice == "2":
        navy_profile = "female"
    elif shape_choice == "3":
        navy_profile = "blend"
        if hrt_type is not None:
            navy_blend_t = hrt_navy_blend_t(hrt_type, hrt_months)
        else:
            navy_profile = "average"   # no HRT info, fall back to 50/50
    elif shape_choice == "4":
        navy_profile = "average"
    else:
        navy_profile = "female"        # safe default

    # ── Body measurements ─────────────────────────────────────
    print("\n── Body Measurements ────────────────────────────────")
    print("  Measure at the widest point, in centimeters.")
    try:
        waist_cm = float(input("  Waist circumference (cm): "))
        neck_cm  = float(input("  Neck circumference (cm): "))
        hip_cm   = None
        if navy_profile in ("female", "average", "blend"):
            hip_cm = float(input("  Hip circumference (cm): "))
    except ValueError:
        print("\n  Invalid input. Please enter numbers only.")
        return

    # ── Activity level ────────────────────────────────────────
    print("\n── Activity Level ───────────────────────────────────")
    print("  1 -- Sedentary   (desk job, little exercise)")
    print("  2 -- Light       (1-3 days/week)")
    print("  3 -- Moderate    (3-5 days/week)")
    print("  4 -- Very active (6-7 days/week)")
    print("  5 -- Extreme     (physical job + daily training)")
    activity_choice = input("\n  Enter choice (1-5): ").strip()
    activity_map    = {
        "1": "sedentary", "2": "light", "3": "moderate",
        "4": "very_active", "5": "extreme",
    }
    activity_level = activity_map.get(activity_choice, "moderate")

    # ── Goal ─────────────────────────────────────────────────
    print("\n── Goal ─────────────────────────────────────────────")
    print("  1 -- Lose weight")
    print("  2 -- Maintain")
    print("  3 -- Gain weight / build muscle")
    goal_choice = input("\n  Enter choice (1-3): ").strip()
    goal_map    = {"1": "lose", "2": "maintain", "3": "gain"}
    goal        = goal_map.get(goal_choice, "maintain")

    # ── Pace of change ────────────────────────────────────────
    pace_kg_per_week = 0.0

    if goal == "lose":
        print("\n── Pace of Weight Loss ──────────────────────────────")
        print("  1 -- Slow      (0.25 kg/week) -- very sustainable,")
        print("                 minimal muscle loss risk")
        print("  2 -- Moderate  (0.50 kg/week) -- recommended for most people")
        print("  3 -- Fast      (0.75 kg/week) -- aggressive, harder to sustain")
        print("  4 -- Very fast (1.00 kg/week) -- maximum safe deficit")
        print("  5 -- Custom    (enter your own kg/week)")
        pace_choice = input("\n  Enter choice (1-5): ").strip()
        presets     = {"1": 0.25, "2": 0.50, "3": 0.75, "4": 1.00}
        if pace_choice == "5":
            try:
                pace_kg_per_week = float(input("  Custom pace (kg/week): "))
            except ValueError:
                pace_kg_per_week = 0.50
        else:
            pace_kg_per_week = presets.get(pace_choice, 0.50)

    elif goal == "gain":
        print("\n── Pace of Weight Gain ──────────────────────────────")
        print("  1 -- Slow      (0.10 kg/week) -- lean bulk, minimal fat gain")
        print("  2 -- Moderate  (0.20 kg/week) -- recommended for most people")
        print("  3 -- Fast      (0.35 kg/week) -- aggressive bulk")
        print("  4 -- Custom    (enter your own kg/week)")
        pace_choice = input("\n  Enter choice (1-4): ").strip()
        presets     = {"1": 0.10, "2": 0.20, "3": 0.35}
        if pace_choice == "4":
            try:
                pace_kg_per_week = float(input("  Custom pace (kg/week): "))
            except ValueError:
                pace_kg_per_week = 0.20
        else:
            pace_kg_per_week = presets.get(pace_choice, 0.20)

    # ── Metabolic conditions ──────────────────────────────────
    print("\n── Metabolic Conditions (optional) ──────────────────")
    print("  Enter any that apply (comma-separated), or press Enter to skip.")
    print()
    for key, cond in CONDITIONS.items():
        print(f"    {key:<35} -> {cond.name}")

    conditions_input = input("\n  Your conditions: ").strip()
    condition_keys   = (
        [c.strip() for c in conditions_input.split(",") if c.strip()]
        if conditions_input else []
    )

    # ── Calculations ──────────────────────────────────────────
    try:
        body_fat_pct = calc_body_fat_navy(
            height_cm, waist_cm, neck_cm, hip_cm,
            profile=navy_profile,
            hrt_blend_t=navy_blend_t,
        )

        if hormonal_profile == "hrt" and hrt_type is not None:
            bmr = interpolate_bmr_hrt(
                weight_kg, height_cm, age,
                hrt_type, hrt_months, body_fat_pct,
            )
        else:
            bmr = calc_bmr(
                weight_kg, height_cm, age,
                profile=hormonal_profile,
                body_fat_pct=body_fat_pct,
            )

        condition_result = apply_metabolic_conditions(bmr, condition_keys)
        adjusted_bmr     = condition_result["adjusted_bmr"]
        requires_consult = condition_result["requires_consult"]

        tdee                   = calc_tdee(adjusted_bmr, activity_level)
        goal_kcal, pace_warning = calc_goal_adjustment(goal, pace_kg_per_week)
        target_kcal            = tdee + goal_kcal
        macros                 = calc_macros(target_kcal, weight_kg, body_fat_pct, goal)

    except (ValueError, ZeroDivisionError) as e:
        print(f"\n  Calculation error: {e}")
        return

    # ── Output ────────────────────────────────────────────────
    print("\n" + "=" * 55)
    print("  RESULTS")
    print("=" * 55)
    print(f"  Body fat %          : {body_fat_pct:.1f}%")
    print(f"  BMR (base)          : {bmr:.0f} kcal/day")

    if hormonal_profile == "hrt" and hrt_type is not None:
        t = _hrt_t(hrt_months, hrt_type)
        print(f"  HRT blend           : {t:.0%} toward target physiology")
        print(f"                        ({hrt_months} mo on {hrt_type})")

    if condition_keys:
        print(f"  BMR (adjusted)      : {adjusted_bmr} kcal/day")

    print(f"  TDEE (maintenance)  : {tdee:.0f} kcal/day")

    if goal != "maintain":
        sign = "-" if goal_kcal < 0 else "+"
        verb = "loss" if goal == "lose" else "gain"
        print(f"  Goal adjustment     : {sign}{abs(goal_kcal):.0f} kcal/day")
        print(f"                        ({pace_kg_per_week} kg/week {verb})")

    print(f"  Target calories     : {target_kcal:.0f} kcal/day")
    print()
    print("  ── Daily Macro Targets ──────────────────────────")
    print(f"  Protein   : {macros['protein_g']} g  ({macros['protein_g'] * 4} kcal)")
    print(f"  Fat       : {macros['fat_g']} g  ({macros['fat_g'] * 9} kcal)")
    print(f"  Carbs     : {macros['carbs_g']} g  ({macros['carbs_g'] * 4} kcal)")
    print()

    if pace_warning:
        print("  ── Pace Warning ─────────────────────────────────")
        print(_wrap(f"! {pace_warning}"))
        print()

    if condition_result["condition_notes"]:
        print("  ── Condition Notes ──────────────────────────────")
        for c in condition_result["condition_notes"]:
            print(f"\n  [{c['condition']}]")
            print(_wrap(c["note"]))
        print()

    if requires_consult:
        print("  ! One or more conditions flagged above require")
        print("    consultation with a registered dietitian or")
        print("    specialist before acting on these numbers.")
        print()

    print("=" * 55 + "\n")


if __name__ == "__main__":
    run_calculator()