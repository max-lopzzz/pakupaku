# Design: Condition Notes, Fibromyalgia, & Bug Fixes
**Date:** 2026-04-18
**Status:** Approved

---

## Overview

Three user-reported issues addressed in one branch:

1. **Decimal rounding** — numbers throughout the app display too many decimal places.
2. **Horizontal overflow on mobile** — certain form layouts cause horizontal scroll on narrow screens.
3. **Condition-specific nutrition notes + fibromyalgia support** — users with metabolic conditions receive tailored guidance during onboarding, on the dashboard, and in generated meal plans. Fibromyalgia is added as a supported condition.

---

## 1. Bug Fix — Decimal Rounding

### Problem
Calories, macros, body stats, and shopping amounts are rendered as raw API values (e.g. `123.456 kcal`, `12.3456g`).

### Fix
Two shared rounding helpers, defined once and imported where needed:

```ts
// src/utils/format.ts
export const round0 = (n: number) => Math.round(n);
export const round1 = (n: number) => Math.round(n * 10) / 10;
```

| Value | Rounding |
|---|---|
| Calories (display) | `round0` — whole numbers only |
| Macros (g) | `round0` — whole grams |
| Body stats: weight, height, body fat % | `round1` — one decimal place |
| Shopping list amounts | `round1` |
| Day total kcal (MealPlanner day tabs) | `round0` |

**Files to update:** `Dashboard.tsx`, `MealPlanner.tsx`, `RecipeBuilder.tsx`.

---

## 2. Bug Fix — Horizontal Overflow on Mobile

### Problem
The "Log measurement" form renders six fields side-by-side regardless of screen width, causing horizontal overflow on phones.

### Fix
Change the measurement row CSS from a fixed flex/grid row to a responsive grid:

```css
.measurement-row {
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
}
```

Additionally audit the category grid and any other fixed-width containers in `Dashboard.css` and `MealPlanner.css` for elements that resist wrapping below 375px. Add `min-width: 0` where needed to prevent grid blowout.

---

## 3. Feature — Condition-Specific Nutrition Notes

### 3a. Data Flow (Approach C)

`metabolic_conditions` is already stored as a `Text` (JSON) column on the `User` model. The only backend change is **deserialising it and exposing it in `UserResponse`**:

```python
# schemas.py — UserResponse
metabolic_conditions: List[str] = Field(default_factory=list)
```

```python
# main.py — /users/me serialisation
# deserialise JSON string → list before returning
```

This makes `userProfile.metabolic_conditions` available everywhere in the frontend with no migration.

### 3b. Frontend Content File

New file: `src/constants/conditionNotes.ts`

Exports `CONDITION_NOTES`: a `Record<string, ConditionNote>` keyed by condition slug.

```ts
interface ConditionNote {
  label:           string;      // Human display name
  onboardingNote:  string;      // 1–2 sentences shown inline when checkbox is ticked
  dashboardNotes:  string[];    // 3–5 bullet points for the dashboard card
  edWarning?:      boolean;     // true = show ED-safe warning if extreme diet selected
}
```

**Conditions and content:**

| Slug | Onboarding note (summary) | Dashboard bullets (summary) |
|---|---|---|
| `hypothyroidism_untreated` | Thyroid function affects metabolism; iodine and selenium support thyroid health. | Prioritise iodine-rich foods (seafood, dairy, eggs); selenium sources (Brazil nuts, tuna); avoid excessive raw cruciferous veg; fibre helps digestion; consult your endocrinologist before major diet changes. |
| `hypothyroidism_treated` | With medication, most foods are fine; timing matters with certain nutrients. | Take thyroid meds away from calcium/iron-rich meals; iodine-containing foods are generally fine; maintain consistent eating times; selenium-rich foods remain beneficial. |
| `hyperthyroidism_untreated` | Your metabolism is running faster than usual; focus on calories and bone health. | Limit iodine-rich foods (seaweed, kelp); increase calcium and vitamin D for bone protection; higher calorie needs until levels stabilise; avoid stimulants (caffeine); work with your doctor on timing. |
| `hyperthyroidism_treated` | Medication brings metabolism closer to normal; prioritise bone density. | Ensure adequate calcium and vitamin D intake; balanced macros; avoid excess caffeine; regular follow-up with your endocrinologist. |
| `hiv_wasting` | Higher protein and calorie needs support muscle and immune function. | Aim for 1.5–2 g protein per kg body weight; calorie-dense, nutrient-rich foods; strict food safety (avoid raw/undercooked); frequent smaller meals if appetite is low; work with a dietitian. |
| `cancer_active` | Nutritional needs vary by treatment phase; protein and easy digestion are priorities. | Prioritise protein to preserve muscle mass; choose easy-to-digest foods during treatment; manage side effects (nausea, taste changes) with texture and temperature adjustments; stay hydrated; a cancer dietitian can personalise this further. |
| `pcos` | A low-GI, anti-inflammatory diet can help manage insulin sensitivity and symptoms. | Favour low-GI carbohydrates (oats, legumes, sweet potato); increase omega-3 foods (salmon, walnuts, flaxseed); limit refined sugars and ultra-processed foods; inositol-rich foods (citrus, beans) may help; regular meal timing supports hormonal balance. |
| `cushings` | Cortisol excess affects fat distribution, blood sugar, and bone density. | Limit sodium (reduces water retention and blood pressure risk); reduce simple carbohydrates; prioritise potassium-rich foods (banana, spinach, avocado); ensure adequate calcium and vitamin D; avoid alcohol. |
| `diabetes_t1` | Consistent carbohydrate intake and timing help with insulin management. | Count and distribute carbohydrates consistently across meals; favour low-GI sources; pair carbs with protein/fat to blunt glucose spikes; stay hydrated; keep fast-acting glucose on hand; your diabetes team can fine-tune targets. |
| `eating_disorder_history` | All foods fit — regular, balanced eating supports both physical and mental wellbeing. | Aim for regular, structured meal times; include all food groups without labelling foods as "bad"; focus on how food makes you feel rather than numbers alone; if distressing thoughts arise, support is available (see below). |
| `fibromyalgia` *(new)* | An anti-inflammatory diet may help manage pain and fatigue. | Increase omega-3 sources (oily fish, chia, flaxseed); choose antioxidant-rich colourful vegetables and berries; magnesium-rich foods (pumpkin seeds, dark chocolate, spinach) may ease muscle tension; ensure adequate vitamin D; limit processed foods, alcohol, and excess caffeine; small regular meals help manage energy. |

### 3c. Eating Disorder History — Diet Warning

When a user with `eating_disorder_history` selects `ketogenic` or another extreme diet in the Meal Planner, **do not block the selection**. Instead, display a soft warning beneath the diet selector:

> ⚠️ Some restrictive diets can be challenging with an eating disorder history. If you need support, [Beat (UK)](https://www.beateatingdisorders.org.uk) · [NEDA (US)](https://www.nationaleatingdisorders.org) are available.

The warning is dismissible and does not prevent plan generation.

### 3d. Onboarding Changes

When a condition checkbox is ticked, the `onboardingNote` expands inline beneath it with a CSS `max-height` transition. It collapses on uncheck. No modal, no tooltip — just a soft mint-background `<p>` consistent with the app's existing palette.

### 3e. Dashboard — HealthNotesCard

A new `HealthNotesCard` component, rendered below "Body Statistics", only when `userProfile.metabolic_conditions.length > 0`.

- Each condition gets a collapsible row with a chevron toggle.
- Rows start **expanded** on first render.
- Content: `dashboardNotes` bullet list.
- Eating disorder history row appends the support resource links at the bottom of its bullet list.
- Styled with existing design tokens (`--paku-mint`, `--paku-bg`, `--paku-text`, `--paku-radius`).

### 3f. Meal Plan Integration

`generate_weekly_plan()` in `spoonacular.py` gains an optional `conditions: List[str]` parameter (defaults to `[]`).

A new `CONDITION_MEAL_HINTS` dict maps each condition slug to meal search adjustments:

```python
CONDITION_MEAL_HINTS = {
  "hypothyroidism_untreated": {
    "exclude_extra": ["seaweed", "kelp"],  # raw goitrogen excess via exclude
  },
  "hyperthyroidism_untreated": {
    "exclude_extra": ["seaweed", "kelp", "nori"],
  },
  "hiv_wasting": {
    "prefer_diet": "highprotein",  # appended to complexSearch tags
  },
  "cancer_active": {
    "prefer_diet": "highprotein",
  },
  "pcos": {
    "prefer_diet": "mediterranean",  # used when user has no diet preference
  },
  "cushings": {
    "exclude_extra": ["soy sauce", "miso", "canned soup"],  # high-sodium proxies
  },
  "fibromyalgia": {
    "prefer_diet": "mediterranean",
  },
  # hypothyroidism_treated, hyperthyroidism_treated, diabetes_t1,
  # eating_disorder_history: no search-level changes
}
```

**Merge logic:**
1. Start with user-provided `diet` and `exclude` strings.
2. For each condition in `conditions`, append `exclude_extra` items to the exclude list.
3. If `diet` is empty/None, use the first `prefer_diet` found across the user's conditions.
4. `eating_disorder_history` does not affect search parameters — the warning is frontend-only.

The `/mealplan/weekly` endpoint deserialises `current_user.metabolic_conditions` and passes it to `generate_weekly_plan()`.

---

## Files Changed

| File | Change |
|---|---|
| `schemas.py` | Add `metabolic_conditions: List[str]` to `UserResponse` |
| `main.py` | Deserialise `metabolic_conditions` JSON before returning `/users/me`; pass conditions to `generate_weekly_plan()` |
| `spoonacular.py` | Add `conditions` param + `CONDITION_MEAL_HINTS` to `generate_weekly_plan()` |
| `nutrition_calculator.py` | Add `fibromyalgia` condition entry |
| `src/constants/conditionNotes.ts` | New file — all condition note content |
| `src/utils/format.ts` | New file — `round0`, `round1` helpers |
| `src/components/Dashboard.tsx` | Use `round0`/`round1`; add `HealthNotesCard`; fix measurement grid |
| `src/components/Dashboard.css` | Responsive measurement row; `HealthNotesCard` styles |
| `src/components/MealPlanner.tsx` | Use `round0`/`round1`; ED warning on extreme diet select |
| `src/components/MealPlanner.css` | ED warning styles |
| `src/components/RecipeBuilder.tsx` | Use `round0`/`round1` (already partially rounded) |
| `src/components/Onboarding.tsx` | Inline condition notes on checkbox tick |
| `src/components/Onboarding.css` | Expand/collapse transition styles |
