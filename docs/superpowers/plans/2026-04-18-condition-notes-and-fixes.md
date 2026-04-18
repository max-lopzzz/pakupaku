# Condition Notes, Fibromyalgia & Bug Fixes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix decimal rounding and mobile overflow bugs, add fibromyalgia as a supported metabolic condition, and surface per-condition nutrition notes in onboarding, the dashboard, and the meal planner.

**Architecture:** Content-first — all note text lives in `src/constants/conditionNotes.ts`; the backend exposes which conditions the user has via `UserResponse.metabolic_conditions` (deserialised from a comma-separated string already stored on the User model); meal-plan diet hints live in `spoonacular.py`. Formatting utilities are extracted to `src/utils/format.ts` so rounding is consistent across all components.

**Tech Stack:** React + TypeScript (frontend), FastAPI + Pydantic v1 + SQLAlchemy async (backend), PostgreSQL, Spoonacular API.

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `src/utils/format.ts` | Create | `round0` / `round1` rounding helpers |
| `src/constants/conditionNotes.ts` | Create | All condition note content + meal hints |
| `src/components/HealthNotesCard.tsx` | Create | Dashboard condition notes card |
| `src/components/HealthNotesCard.css` | Create | HealthNotesCard styles |
| `src/components/Dashboard.tsx` | Modify | Use rounding helpers; add HealthNotesCard; fix measurement grid |
| `src/components/Dashboard.css` | Modify | Responsive measurement row |
| `src/components/MealPlanner.tsx` | Modify | Use rounding helpers; ED warning |
| `src/components/MealPlanner.css` | Modify | ED warning styles |
| `src/components/RecipeBuilder.tsx` | Modify | Use rounding helpers |
| `src/components/Onboarding.tsx` | Modify | Add fibromyalgia; inline notes on pill select |
| `src/components/Onboarding.css` | Modify | Note expand/collapse transition |
| `schemas.py` | Modify | Add `metabolic_conditions: List[str]` to `UserResponse` |
| `main.py` | Modify | Deserialise conditions; pass to `generate_weekly_plan` |
| `nutrition_calculator.py` | Modify | Add fibromyalgia condition entry |
| `spoonacular.py` | Modify | Add `conditions` param + `CONDITION_MEAL_HINTS` |

---

## Task 1: Rounding helpers

**Files:**
- Create: `pakupaku-frontend/src/utils/format.ts`

- [ ] **Step 1: Create the file**

```ts
// pakupaku-frontend/src/utils/format.ts

/** Round to nearest whole number (calories, macro grams). */
export const round0 = (n: number | null | undefined): number =>
  Math.round(n ?? 0);

/** Round to one decimal place (weight kg, height cm, body fat %). */
export const round1 = (n: number | null | undefined): number =>
  Math.round((n ?? 0) * 10) / 10;
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd pakupaku-frontend && npx tsc --noEmit
```
Expected: no output (no errors).

- [ ] **Step 3: Commit**

```bash
git add pakupaku-frontend/src/utils/format.ts
git commit -m "feat: add round0/round1 formatting helpers"
```

---

## Task 2: Apply rounding in Dashboard.tsx

**Files:**
- Modify: `pakupaku-frontend/src/components/Dashboard.tsx`

- [ ] **Step 1: Import helpers at the top of Dashboard.tsx**

After the existing imports, add:
```ts
import { round0, round1 } from "../utils/format";
```

- [ ] **Step 2: Fix calorie / macro display**

In the "Calorie Progress" section replace the raw values:
```tsx
// Before
<strong>{totalConsumed.calories} / {nutritionData.calories.goal} cal</strong>
// After
<strong>{round0(totalConsumed.calories)} / {round0(nutritionData.calories.goal)} cal</strong>
```

In the "Macro Progress" nutrition cards do the same for all four macros:
```tsx
// Calories card
{round0(totalConsumed.calories)} / {round0(nutritionData.calories.goal)}
// Protein card
{round0(totalConsumed.protein)}g / {round0(nutritionData.protein.goal)}g
// Carbs card
{round0(totalConsumed.carbs)}g / {round0(nutritionData.carbs.goal)}g
// Fat card
{round0(totalConsumed.fat)}g / {round0(nutritionData.fat.goal)}g
```

- [ ] **Step 3: Fix body stats display**

Find the body-stats section. Replace:
```tsx
// Before
<span className="stat-value">{weight != null ? `${weight} kg` : "N/A"}</span>
<span className="stat-value">{height != null ? `${height} cm` : "N/A"}</span>
<span className="stat-value">{bf != null ? `${bf}%` : "N/A"}</span>
// After
<span className="stat-value">{weight != null ? `${round1(weight)} kg` : "N/A"}</span>
<span className="stat-value">{height != null ? `${round1(height)} cm` : "N/A"}</span>
<span className="stat-value">{bf != null ? `${round1(bf)}%` : "N/A"}</span>
```

- [ ] **Step 4: Fix meal card macros**

In the meal cards (inside `mealsByCategory.map`), replace raw values:
```tsx
// Before
<span className="macro-item">{meal.calories} cal</span>
<span className="macro-item">{meal.protein}g P</span>
<span className="macro-item">{meal.carbs}g C</span>
<span className="macro-item">{meal.fat}g F</span>
// After
<span className="macro-item">{round0(meal.calories)} cal</span>
<span className="macro-item">{round0(meal.protein)}g P</span>
<span className="macro-item">{round0(meal.carbs)}g C</span>
<span className="macro-item">{round0(meal.fat)}g F</span>
```

Also fix the category consumed / goal display:
```tsx
// Before
<p>{category.consumed} / {category.goal} cal</p>
// After
<p>{round0(category.consumed)} / {round0(category.goal)} cal</p>
```

- [ ] **Step 5: Verify TypeScript compiles**

```bash
cd pakupaku-frontend && npx tsc --noEmit
```
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add pakupaku-frontend/src/components/Dashboard.tsx
git commit -m "fix: round calories and macros in Dashboard"
```

---

## Task 3: Apply rounding in MealPlanner.tsx

**Files:**
- Modify: `pakupaku-frontend/src/components/MealPlanner.tsx`

- [ ] **Step 1: Import helpers**

```ts
import { round0, round1 } from "../utils/format";
```

- [ ] **Step 2: Fix macro badges in MealCard**

```tsx
// Before
<span className="mp-macro mp-macro--cal">{meal.calories} kcal</span>
<span className="mp-macro mp-macro--p">{meal.protein_g}g P</span>
<span className="mp-macro mp-macro--c">{meal.carbs_g}g C</span>
<span className="mp-macro mp-macro--f">{meal.fat_g}g F</span>
// After
<span className="mp-macro mp-macro--cal">{round0(meal.calories)} kcal</span>
<span className="mp-macro mp-macro--p">{round0(meal.protein_g)}g P</span>
<span className="mp-macro mp-macro--c">{round0(meal.carbs_g)}g C</span>
<span className="mp-macro mp-macro--f">{round0(meal.fat_g)}g F</span>
```

- [ ] **Step 3: Fix day-tab calorie display**

```tsx
// Before
<span className="mp-day-kcal">{d.total_calories} kcal</span>
// After
<span className="mp-day-kcal">{round0(d.total_calories)} kcal</span>
```

- [ ] **Step 4: Fix shopping list amounts**

```tsx
// Before
<span className="mp-shopping-amount">{item.amount} {item.unit}</span>
// After
<span className="mp-shopping-amount">{round1(item.amount)} {item.unit}</span>
```

- [ ] **Step 5: Compile check**

```bash
cd pakupaku-frontend && npx tsc --noEmit
```

- [ ] **Step 6: Commit**

```bash
git add pakupaku-frontend/src/components/MealPlanner.tsx
git commit -m "fix: round calories, macros, and amounts in MealPlanner"
```

---

## Task 4: Apply rounding in RecipeBuilder.tsx

**Files:**
- Modify: `pakupaku-frontend/src/components/RecipeBuilder.tsx`

- [ ] **Step 1: Import helpers**

```ts
import { round0, round1 } from "../utils/format";
```

- [ ] **Step 2: Find any remaining raw number displays**

Search for patterns like `{food.calories`, `{ing.calories`, `{total` in RecipeBuilder.tsx. Replace any that are not already wrapped in `Math.round()` with the appropriate helper:
- Calorie / macro values → `round0(...)`
- Per-100g amounts → `round1(...)`

Replace existing `Math.round(...)` calls with the equivalent helper for consistency:
```tsx
// Before (example)
{Math.round(food.calories_per_100g)}
// After
{round0(food.calories_per_100g)}
```

- [ ] **Step 3: Compile check**

```bash
cd pakupaku-frontend && npx tsc --noEmit
```

- [ ] **Step 4: Commit**

```bash
git add pakupaku-frontend/src/components/RecipeBuilder.tsx
git commit -m "fix: use shared rounding helpers in RecipeBuilder"
```

---

## Task 5: Fix horizontal overflow on mobile

**Files:**
- Modify: `pakupaku-frontend/src/components/Dashboard.css`

- [ ] **Step 1: Make the measurement form responsive**

Find `.measurement-row` in `Dashboard.css`. Replace its layout with a responsive grid:

```css
.measurement-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 0.75rem;
}
```

- [ ] **Step 2: Prevent grid blowout on very narrow screens**

Find `.body-stats-grid` and `.nutrition-grid` and add `min-width: 0` to their children to prevent overflow when grid items contain long text:

```css
.body-stats-grid > *,
.nutrition-grid > * {
  min-width: 0;
}
```

- [ ] **Step 3: Verify no other fixed-width elements**

Search Dashboard.css for any `width: <number>px` values wider than 320px and verify they are inside a media query or have `max-width` rather than `width`. Add `max-width: 100%` where needed.

- [ ] **Step 4: Commit**

```bash
git add pakupaku-frontend/src/components/Dashboard.css
git commit -m "fix: responsive measurement form and grid overflow on mobile"
```

---

## Task 6: Add fibromyalgia to the backend

**Files:**
- Modify: `nutrition_calculator.py`

- [ ] **Step 1: Add the fibromyalgia entry to CONDITIONS**

Open `nutrition_calculator.py`. After the `"eating_disorder_history"` entry (line ~159), and before the closing `}`, add:

```python
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
```

- [ ] **Step 2: Restart the backend and verify it starts cleanly**

```bash
# In the backend directory with .venv active:
uvicorn main:app --reload
```
Expected: `Application startup complete.` with no tracebacks.

- [ ] **Step 3: Commit**

```bash
git add nutrition_calculator.py
git commit -m "feat: add fibromyalgia as a supported metabolic condition"
```

---

## Task 7: Expose metabolic_conditions in UserResponse

**Files:**
- Modify: `schemas.py`
- Modify: `main.py`

- [ ] **Step 1: Add the field to UserResponse in schemas.py**

`metabolic_conditions` is stored as a comma-separated string on the User model (e.g. `"pcos,fibromyalgia"`). Add a validator that splits it:

```python
# In schemas.py, inside UserResponse, add this field + validator:
metabolic_conditions: List[str] = Field(default_factory=list)

@validator("metabolic_conditions", pre=True, always=True)
def parse_conditions(cls, v):
    if not v:
        return []
    if isinstance(v, list):
        return v
    # stored as comma-separated string
    return [c.strip() for c in str(v).split(",") if c.strip()]
```

Make sure `List` is imported from `typing` (it already is in schemas.py).

- [ ] **Step 2: Pass conditions to generate_weekly_plan in main.py**

Find the `/mealplan/weekly` endpoint. After retrieving `target_kcal`, deserialise the user's conditions and pass them:

```python
# In the /mealplan/weekly handler, before calling generate_weekly_plan:
raw_conditions = current_user.metabolic_conditions or ""
conditions = [c.strip() for c in raw_conditions.split(",") if c.strip()]

return await generate_weekly_plan(int(target_kcal), diet, exclude, conditions)
```

- [ ] **Step 3: Restart backend and verify /users/me returns conditions**

With the backend running, log in and call:
```bash
curl -s http://localhost:8000/users/me \
  -H "Authorization: Bearer <your_token>" | python3 -m json.tool | grep metabolic
```
Expected: `"metabolic_conditions": []` (or your test user's conditions as a list).

- [ ] **Step 4: Commit**

```bash
git add schemas.py main.py
git commit -m "feat: expose metabolic_conditions list in UserResponse"
```

---

## Task 8: Add CONDITION_MEAL_HINTS to spoonacular.py

**Files:**
- Modify: `spoonacular.py`

- [ ] **Step 1: Add the hints dict near the top of spoonacular.py (after imports)**

```python
from typing import Dict, List, Optional, Set, Tuple, Union

# ── Condition meal hints ──────────────────────────────────────
# Maps metabolic condition slugs to Spoonacular search adjustments.
# prefer_diet is used only when the user hasn't selected a diet filter.
# exclude_extra items are always appended to the exclude list.

CONDITION_MEAL_HINTS: Dict[str, Dict[str, object]] = {
    "hypothyroidism_untreated": {
        "exclude_extra": ["seaweed", "kelp", "nori"],
    },
    "hyperthyroidism_untreated": {
        "exclude_extra": ["seaweed", "kelp", "nori", "iodized salt"],
    },
    "hiv_wasting": {
        "prefer_diet": "highprotein",
    },
    "cancer_active": {
        "prefer_diet": "highprotein",
    },
    "pcos": {
        "prefer_diet": "mediterranean",
    },
    "cushings": {
        "exclude_extra": ["soy sauce", "miso", "canned soup", "pickles"],
    },
    "fibromyalgia": {
        "prefer_diet": "mediterranean",
    },
    # hypothyroidism_treated, hyperthyroidism_treated, diabetes_t1,
    # eating_disorder_history: no search-level changes
}
```

- [ ] **Step 2: Update generate_weekly_plan signature and apply hints**

Find `async def generate_weekly_plan(target_calories, diet, exclude)` and update it:

```python
async def generate_weekly_plan(
    target_calories: int,
    diet:       Optional[str] = None,
    exclude:    Optional[str] = None,
    conditions: Optional[List[str]] = None,
) -> dict:
    """
    Generate a 7-day meal plan tailored to the given calorie target.
    Applies condition-specific dietary hints when conditions are provided.
    ...
    """
    conditions = conditions or []

    # Build effective diet and exclude from conditions
    effective_diet = diet  # user choice takes priority
    extra_excludes: List[str] = []

    for cond in conditions:
        hints = CONDITION_MEAL_HINTS.get(cond, {})
        if not effective_diet and hints.get("prefer_diet"):
            effective_diet = str(hints["prefer_diet"])
        extra_excludes.extend(hints.get("exclude_extra", []))  # type: ignore

    # Merge with any user-provided exclude list
    if extra_excludes:
        existing = [e.strip() for e in (exclude or "").split(",") if e.strip()]
        combined = existing + extra_excludes
        effective_exclude: Optional[str] = ",".join(combined)
    else:
        effective_exclude = exclude if exclude else None

    # Replace all references to `diet` and `exclude` in the rest of
    # the function body with `effective_diet` and `effective_exclude`.
    # (search for the four search_recipes_for_meal calls and update the args)
```

In the body of `generate_weekly_plan`, find the four `search_recipes_for_meal(...)` calls and make sure they pass `effective_diet` and `effective_exclude` instead of `diet` and `exclude`.

- [ ] **Step 3: Restart backend, verify it imports cleanly**

```bash
uvicorn main:app --reload
```
Expected: `Application startup complete.` with no tracebacks.

- [ ] **Step 4: Commit**

```bash
git add spoonacular.py
git commit -m "feat: apply condition meal hints in generate_weekly_plan"
```

---

## Task 9: Create conditionNotes.ts

**Files:**
- Create: `pakupaku-frontend/src/constants/conditionNotes.ts`

- [ ] **Step 1: Create the file with all 11 conditions**

```ts
// pakupaku-frontend/src/constants/conditionNotes.ts

export interface ConditionNote {
  label:          string;
  onboardingNote: string;   // shown inline when pill is selected in Onboarding
  dashboardNotes: string[]; // bullet points on the dashboard Health Notes card
  edWarning?:     boolean;  // if true, show ED warning in MealPlanner for extreme diets
}

export const CONDITION_NOTES: Record<string, ConditionNote> = {
  hypothyroidism_untreated: {
    label: "Hypothyroidism (untreated)",
    onboardingNote:
      "Thyroid function can significantly lower your resting metabolism. " +
      "Iodine and selenium support thyroid health — your goals will reflect this.",
    dashboardNotes: [
      "Prioritise iodine-rich foods: seafood, dairy, and eggs.",
      "Include selenium sources: Brazil nuts (1–2/day), tuna, and sunflower seeds.",
      "Avoid excessive raw cruciferous vegetables (broccoli, kale, cauliflower) — cooking deactivates goitrogens.",
      "Fibre-rich foods help with the digestive slowdown common in hypothyroidism.",
      "Consult your endocrinologist before making major dietary changes.",
    ],
  },
  hypothyroidism_treated: {
    label: "Hypothyroidism (treated)",
    onboardingNote:
      "With medication, your metabolism is likely closer to normal. " +
      "A few timing and nutrient considerations still apply.",
    dashboardNotes: [
      "Take thyroid medication at least 30–60 min before calcium or iron-rich meals.",
      "Iodine-containing foods are generally fine in normal amounts.",
      "Selenium-rich foods (Brazil nuts, tuna) remain beneficial.",
      "Maintain consistent meal timing to support stable hormone levels.",
    ],
  },
  hyperthyroidism_untreated: {
    label: "Hyperthyroidism (untreated)",
    onboardingNote:
      "Your metabolism is running faster than usual, raising calorie needs " +
      "and increasing bone-loss risk. Your goals account for this.",
    dashboardNotes: [
      "Limit iodine-rich foods: seaweed, kelp, and nori, as iodine can worsen hyperthyroidism.",
      "Increase calcium and vitamin D to protect bones (dairy, fortified plant milks, leafy greens).",
      "Higher calorie needs until thyroid levels are controlled — do not restrict aggressively.",
      "Avoid excess caffeine, which can worsen heart-rate symptoms.",
      "Work closely with your endocrinologist on timing of treatment and diet.",
    ],
  },
  hyperthyroidism_treated: {
    label: "Hyperthyroidism (treated)",
    onboardingNote:
      "Medication brings metabolism closer to normal. Bone density remains " +
      "a priority even after levels stabilise.",
    dashboardNotes: [
      "Ensure adequate calcium (1000–1200 mg/day) and vitamin D for bone health.",
      "Balanced macronutrients — no specific restrictions once levels are controlled.",
      "Moderate caffeine intake.",
      "Regular check-ins with your endocrinologist to monitor levels.",
    ],
  },
  hiv_wasting: {
    label: "HIV/AIDS with wasting",
    onboardingNote:
      "Higher protein and calorie needs are built into your targets to " +
      "support immune function and muscle preservation.",
    dashboardNotes: [
      "Aim for 1.5–2 g of protein per kg of body weight daily.",
      "Choose calorie-dense, nutrient-rich foods: nuts, nut butters, avocado, oily fish.",
      "Food safety is critical — avoid raw or undercooked meat, fish, and eggs.",
      "Frequent smaller meals can help if appetite is reduced.",
      "A dietitian specialising in HIV care can provide personalised guidance.",
    ],
  },
  cancer_active: {
    label: "Cancer (active)",
    onboardingNote:
      "Nutritional needs vary by cancer type and treatment phase. " +
      "Your targets prioritise protein and nutrient density.",
    dashboardNotes: [
      "Prioritise protein to preserve muscle mass during treatment.",
      "Choose easy-to-digest foods if experiencing nausea or mouth sores.",
      "Experiment with temperature and texture — cold or room-temperature foods are often better tolerated.",
      "Stay well hydrated, especially during chemotherapy or radiation.",
      "An oncology dietitian can tailor recommendations to your specific treatment.",
    ],
  },
  pcos: {
    label: "PCOS",
    onboardingNote:
      "A low-GI, anti-inflammatory diet can improve insulin sensitivity " +
      "and help manage PCOS symptoms alongside your calorie targets.",
    dashboardNotes: [
      "Favour low-GI carbohydrates: oats, legumes, sweet potato, and whole grains.",
      "Increase omega-3 sources: oily fish (salmon, sardines), walnuts, and flaxseed.",
      "Limit refined sugars and ultra-processed foods.",
      "Inositol-rich foods (citrus, beans, whole grains) may support hormonal balance.",
      "Regular, evenly spaced meals help stabilise blood sugar throughout the day.",
    ],
  },
  cushings: {
    label: "Cushing's Syndrome",
    onboardingNote:
      "Cortisol excess affects fat distribution, blood pressure, and bone " +
      "density. Your meal plan reflects lower-sodium, bone-supportive guidance.",
    dashboardNotes: [
      "Limit sodium: avoid processed foods, soy sauce, canned soups, and pickles.",
      "Reduce simple carbohydrates to support blood sugar management.",
      "Prioritise potassium-rich foods: banana, spinach, avocado, and sweet potato.",
      "Ensure adequate calcium and vitamin D for bone protection.",
      "Avoid alcohol, which worsens cortisol-related metabolic effects.",
    ],
  },
  diabetes_t1: {
    label: "Type 1 Diabetes",
    onboardingNote:
      "Consistent carbohydrate intake and timing work alongside insulin " +
      "management. Your targets support steady blood sugar, not elimination of carbs.",
    dashboardNotes: [
      "Distribute carbohydrates consistently across meals rather than skipping them.",
      "Favour low-GI carbohydrate sources to reduce blood glucose spikes.",
      "Pair carbohydrates with protein or fat to blunt the glucose response.",
      "Keep fast-acting glucose (juice, glucose tablets) accessible at all times.",
      "Your diabetes care team can fine-tune your targets and insulin-to-carb ratio.",
    ],
  },
  eating_disorder_history: {
    label: "Eating disorder history",
    onboardingNote:
      "All foods fit — regular, balanced eating supports both physical and " +
      "mental wellbeing. Calorie counts are a guide, not a rule.",
    dashboardNotes: [
      "Aim for regular, structured meal times to build a consistent relationship with food.",
      "Include all food groups — no foods are forbidden here.",
      "Focus on how food makes you feel rather than numbers alone.",
      "If difficult thoughts arise around eating, support is available: " +
        "Beat (UK) beateatingdisorders.org.uk · NEDA (US) nationaleatingdisorders.org · " +
        "ANAD (US) anad.org",
    ],
    edWarning: true,
  },
  fibromyalgia: {
    label: "Fibromyalgia",
    onboardingNote:
      "An anti-inflammatory diet may help manage pain and fatigue. " +
      "Your targets account for potentially reduced activity tolerance.",
    dashboardNotes: [
      "Increase omega-3 sources: oily fish (salmon, mackerel), chia seeds, and flaxseed.",
      "Choose antioxidant-rich foods: colourful vegetables, berries, and green tea.",
      "Magnesium-rich foods may ease muscle tension: pumpkin seeds, dark chocolate, spinach, and almonds.",
      "Ensure adequate vitamin D — consider discussing supplementation with your doctor.",
      "Limit processed foods, excess alcohol, and caffeine, which can worsen fatigue and disrupt sleep.",
      "Small, regular meals help sustain energy across the day.",
    ],
  },
};
```

- [ ] **Step 2: Compile check**

```bash
cd pakupaku-frontend && npx tsc --noEmit
```
Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add pakupaku-frontend/src/constants/conditionNotes.ts
git commit -m "feat: add condition notes content for all 11 metabolic conditions"
```

---

## Task 10: Onboarding — inline notes + fibromyalgia pill

**Files:**
- Modify: `pakupaku-frontend/src/components/Onboarding.tsx`
- Modify: `pakupaku-frontend/src/components/Onboarding.css`

- [ ] **Step 1: Add fibromyalgia to CONDITIONS_LIST in Onboarding.tsx**

Find the `CONDITIONS_LIST` array and append fibromyalgia:

```ts
const CONDITIONS_LIST = [
  { key: "hypothyroidism_untreated", label: "Hypothyroidism (untreated)" },
  { key: "hypothyroidism_treated",   label: "Hypothyroidism (treated)" },
  { key: "hyperthyroidism_untreated",label: "Hyperthyroidism (untreated)" },
  { key: "hyperthyroidism_treated",  label: "Hyperthyroidism (treated)" },
  { key: "hiv_wasting",              label: "HIV/AIDS with wasting" },
  { key: "cancer_active",            label: "Cancer (active)" },
  { key: "pcos",                     label: "PCOS" },
  { key: "cushings",                 label: "Cushing's Syndrome" },
  { key: "diabetes_t1",              label: "Type 1 Diabetes" },
  { key: "eating_disorder_history",  label: "Eating disorder history" },
  { key: "fibromyalgia",             label: "Fibromyalgia" },
];
```

- [ ] **Step 2: Import CONDITION_NOTES**

At the top of Onboarding.tsx, add:
```ts
import { CONDITION_NOTES } from "../constants/conditionNotes";
```

- [ ] **Step 3: Update StepConditions to show inline notes**

Find `StepConditions`. Replace the conditions-grid block:

```tsx
// Before
<div className="conditions-grid">
  {CONDITIONS_LIST.map(c => (
    <HeartBtn key={c.key} selected={form.conditions.includes(c.key)}
      onClick={() => toggleCondition(c.key)} pill>
      {c.label}
    </HeartBtn>
  ))}
</div>

// After
<div className="conditions-list">
  {CONDITIONS_LIST.map(c => {
    const selected = form.conditions.includes(c.key);
    const note = CONDITION_NOTES[c.key];
    return (
      <div key={c.key} className="condition-item">
        <HeartBtn selected={selected} onClick={() => toggleCondition(c.key)} pill>
          {c.label}
        </HeartBtn>
        {selected && note && (
          <p className="condition-inline-note">{note.onboardingNote}</p>
        )}
      </div>
    );
  })}
</div>
```

- [ ] **Step 4: Add CSS for inline notes in Onboarding.css**

Append to `Onboarding.css`:

```css
/* ── Condition inline notes ─────────────────────────────── */
.conditions-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  width: 100%;
}

.condition-item {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.condition-inline-note {
  font-size: 0.85rem;
  color: var(--paku-text, #3a2a2a);
  background: var(--paku-mint, #badfdb);
  border-radius: var(--paku-radius-sm, 12px);
  padding: 0.5rem 0.75rem;
  margin: 0;
  line-height: 1.5;
  animation: note-fade-in 0.2s ease;
}

@keyframes note-fade-in {
  from { opacity: 0; transform: translateY(-4px); }
  to   { opacity: 1; transform: translateY(0); }
}
```

- [ ] **Step 5: Compile check**

```bash
cd pakupaku-frontend && npx tsc --noEmit
```
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add pakupaku-frontend/src/components/Onboarding.tsx \
        pakupaku-frontend/src/components/Onboarding.css
git commit -m "feat: inline condition notes and fibromyalgia pill in onboarding"
```

---

## Task 11: Dashboard — HealthNotesCard

**Files:**
- Create: `pakupaku-frontend/src/components/HealthNotesCard.tsx`
- Create: `pakupaku-frontend/src/components/HealthNotesCard.css`
- Modify: `pakupaku-frontend/src/components/Dashboard.tsx`

- [ ] **Step 1: Create HealthNotesCard.tsx**

```tsx
// pakupaku-frontend/src/components/HealthNotesCard.tsx
import { useState } from "react";
import { CONDITION_NOTES } from "../constants/conditionNotes";
import "./HealthNotesCard.css";

interface HealthNotesCardProps {
  conditions: string[];
}

export default function HealthNotesCard({ conditions }: HealthNotesCardProps) {
  const known = conditions.filter(c => CONDITION_NOTES[c]);
  if (known.length === 0) return null;

  return (
    <div className="hnc-root">
      <h2 className="hnc-title">Health Notes</h2>
      {known.map(key => (
        <ConditionRow key={key} conditionKey={key} />
      ))}
    </div>
  );
}

function ConditionRow({ conditionKey }: { conditionKey: string }) {
  const [open, setOpen] = useState(true);
  const note = CONDITION_NOTES[conditionKey];
  if (!note) return null;

  return (
    <div className="hnc-row">
      <button
        className="hnc-row-header"
        onClick={() => setOpen(o => !o)}
        aria-expanded={open}
      >
        <span className="hnc-row-label">{note.label}</span>
        <span className="hnc-chevron">{open ? "▲" : "▼"}</span>
      </button>
      {open && (
        <ul className="hnc-notes">
          {note.dashboardNotes.map((bullet, i) => (
            <li key={i}>{bullet}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Create HealthNotesCard.css**

```css
/* pakupaku-frontend/src/components/HealthNotesCard.css */

.hnc-root {
  background: var(--paku-white, #fff);
  border-radius: var(--paku-radius, 20px);
  padding: 1.25rem;
  box-shadow: 0 2px 8px rgba(58, 42, 42, 0.07);
  margin-bottom: 1.5rem;
}

.hnc-title {
  font-size: 1.1rem;
  font-weight: 700;
  color: var(--paku-text, #3a2a2a);
  margin: 0 0 1rem;
}

.hnc-row {
  border-top: 1px solid #f0ede0;
  padding: 0.6rem 0;
}

.hnc-row:first-of-type {
  border-top: none;
}

.hnc-row-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
  background: none;
  border: none;
  padding: 0;
  cursor: pointer;
  font-family: inherit;
  text-align: left;
}

.hnc-row-label {
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--paku-text, #3a2a2a);
}

.hnc-chevron {
  font-size: 0.7rem;
  color: var(--paku-muted, #8a6060);
  flex-shrink: 0;
}

.hnc-notes {
  margin: 0.5rem 0 0;
  padding-left: 1.2rem;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.hnc-notes li {
  font-size: 0.88rem;
  color: var(--paku-text, #3a2a2a);
  line-height: 1.5;
}
```

- [ ] **Step 3: Add HealthNotesCard to Dashboard.tsx**

Import the component:
```ts
import HealthNotesCard from "./HealthNotesCard";
```

In the JSX, after the Body Statistics `</section>` closing tag and before the category section, add:
```tsx
<HealthNotesCard conditions={userProfile?.metabolic_conditions ?? []} />
```

- [ ] **Step 4: Compile check**

```bash
cd pakupaku-frontend && npx tsc --noEmit
```
Expected: no output.

- [ ] **Step 5: Commit**

```bash
git add pakupaku-frontend/src/components/HealthNotesCard.tsx \
        pakupaku-frontend/src/components/HealthNotesCard.css \
        pakupaku-frontend/src/components/Dashboard.tsx
git commit -m "feat: HealthNotesCard on dashboard for condition-specific nutrition guidance"
```

---

## Task 12: MealPlanner — eating disorder diet warning

**Files:**
- Modify: `pakupaku-frontend/src/components/MealPlanner.tsx`
- Modify: `pakupaku-frontend/src/components/MealPlanner.css`

- [ ] **Step 1: Import CONDITION_NOTES in MealPlanner.tsx**

```ts
import { CONDITION_NOTES } from "../constants/conditionNotes";
```

- [ ] **Step 2: Determine whether the ED warning applies**

In the `MealPlanner` component, after the existing state declarations, add:

```tsx
const hasEdHistory = (userProfile?.metabolic_conditions ?? [])
  .includes("eating_disorder_history");

const EXTREME_DIETS = new Set(["ketogenic", "paleo"]);
const showEdWarning = hasEdHistory && EXTREME_DIETS.has(diet);
```

- [ ] **Step 3: Render the warning below the diet selector**

In the controls section, after the `<select>` for diet and before the generate button, add:

```tsx
{showEdWarning && (
  <div className="mp-ed-warning" role="alert">
    ⚠️ Some restrictive diets can be challenging with an eating disorder
    history. Support is available:{" "}
    <a href="https://www.beateatingdisorders.org.uk" target="_blank" rel="noreferrer">
      Beat (UK)
    </a>{" "}
    ·{" "}
    <a href="https://www.nationaleatingdisorders.org" target="_blank" rel="noreferrer">
      NEDA (US)
    </a>
  </div>
)}
```

- [ ] **Step 4: Add warning styles to MealPlanner.css**

```css
/* ── ED diet warning ─────────────────────────────────────── */
.mp-ed-warning {
  width: 100%;
  padding: 0.65rem 0.9rem;
  border-radius: var(--paku-radius-sm, 12px);
  background: #fff8e1;
  border: 1.5px solid #ffe082;
  font-size: 0.88rem;
  color: #5d4037;
  line-height: 1.5;
}

.mp-ed-warning a {
  color: #5d4037;
  font-weight: 600;
}

.mp-ed-warning a:hover {
  text-decoration: underline;
}
```

- [ ] **Step 5: Compile check**

```bash
cd pakupaku-frontend && npx tsc --noEmit
```
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add pakupaku-frontend/src/components/MealPlanner.tsx \
        pakupaku-frontend/src/components/MealPlanner.css
git commit -m "feat: ED history diet warning with support resources in MealPlanner"
```

---

## Final verification

- [ ] Both servers running: `uvicorn main:app --reload` + `npm start`
- [ ] Log in → Dashboard: all numbers are rounded; body stats show values (not N/A if onboarding was completed)
- [ ] Dashboard: if user has conditions, Health Notes card appears below Body Statistics with collapsible rows
- [ ] Onboarding conditions step: tapping fibromyalgia shows inline note in mint background; tapping again hides it
- [ ] Measurement form on mobile (375px): six fields wrap into a responsive grid, no horizontal scroll
- [ ] MealPlanner: selecting Keto or Paleo with ED history active shows yellow warning with resource links
- [ ] MealPlanner: generating a plan for a PCOS/fibromyalgia user without a diet preference uses Mediterranean style

- [ ] **Final commit (if any uncommitted changes remain)**

```bash
git add -p   # review before staging
git commit -m "chore: final cleanup for condition-notes feature"
```
