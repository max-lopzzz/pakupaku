# Bulk Recipe Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an admin paste a blog index/archive URL and bulk-extract every recipe linked from it into the shared recipe library, reusing the existing single-URL import pipeline per discovered link.

**Architecture:** A new `recipe_bulk_import.py` module adds link discovery (HTML scraping + heuristic filtering) and concurrency-bounded batch extraction on top of `recipe_import.py`'s unchanged `build_import_draft()`. Two new admin-gated FastAPI routes expose discover/extract as separate calls so the frontend can show a candidate count before committing to the (potentially slow) extraction pass. On the frontend, the per-recipe editing UI already in `RecipeBuilder.tsx` is extracted into a shared `RecipeEditForm.tsx` component so a new `BulkRecipeImport.tsx` screen can drive the same ingredient-matching/editing UI through a one-at-a-time review queue.

**Tech Stack:** FastAPI + SQLAlchemy async (Python 3.8 on the Render deployment — **no `X | None` union syntax**, use `typing.Optional`/`typing.List`), Pydantic v1-style `BaseModel`, BeautifulSoup + httpx (already used by `recipe_import.py`), React 19 + TypeScript CRA frontend, `apiFetch()` for all network calls, `@testing-library/react` for frontend tests, `pytest` with `asyncio_mode = auto`.

**Spec:** [docs/superpowers/specs/2026-08-27-bulk-recipe-import-design.md](../specs/2026-08-27-bulk-recipe-import-design.md)

## Global Constraints

- Production runs **Python 3.8** (confirmed from a live Render traceback this session) — every new backend function signature and type hint must use `typing.Optional[X]` / `typing.List[X]`, never PEP 604 `X | None` union syntax.
- Extraction concurrency is bounded to **5** in-flight `build_import_draft()` calls at once (`asyncio.Semaphore(5)`), matching the spec's stated bound. No cap on total candidate-link count.
- Both new routes (`POST /recipes/bulk-import/discover`, `POST /recipes/bulk-import/extract`) return `403 Forbidden` for any non-admin (`not current_user.is_admin`), with `detail="Admin access required."` — the codebase has no prior route-level `403` gate to copy, so this exact message and status establish the pattern.
- Discovery and extraction are two separate endpoints, not one combined call — this is what lets the frontend show the candidate count and require confirmation before the (LLM-calling, potentially slow) extraction pass runs.
- No streaming/progress feedback during extraction — the frontend shows one loading state for the whole batch and waits for the single `POST /recipes/bulk-import/extract` response, consistent with every other route in this app.
- The bulk-import review queue pre-checks `is_shared: true` on every draft by default (unlike single-recipe import, which defaults it unchecked) — still per-recipe editable via the same admin-only checkbox.
- The `RecipeEditForm.tsx` extraction from `RecipeBuilder.tsx` must be **behavior-preserving**: `RecipeBuilder.test.tsx`'s four existing tests must pass unchanged after the refactor, with no new test added to that file for this plan (its coverage is the refactor's regression check).
- No link-count cap and no pagination-following — one index page's discovered links per run, non-goals per the spec.
- **Known risk to verify, not preempt:** Render's free-tier HTTP proxy may have a response timeout shorter than a large uncapped batch's worst case (candidates × up to ~40s each, partly offset by concurrency=5). No task in this plan builds around this speculatively — it's flagged here so whoever tests against a real large batch post-merge knows what a timeout symptom would mean and that the fix, if needed, is revisiting the synchronous-extraction decision above, not a code defect.

---

### Task 1: Extract `RecipeEditForm.tsx` from `RecipeBuilder.tsx`

**Files:**
- Create: `pakupaku-frontend/src/components/RecipeEditForm.tsx`
- Modify: `pakupaku-frontend/src/components/RecipeBuilder.tsx` (full rewrite)
- Test (regression, unchanged): `pakupaku-frontend/src/components/RecipeBuilder.test.tsx`

**Interfaces:**
- Produces (from `RecipeEditForm.tsx`, all `export`ed, consumed by Task 5's `BulkRecipeImport.tsx` and by the rewritten `RecipeBuilder.tsx`):
  - `interface IngredientRow` — unchanged shape, moved as-is.
  - `interface RecipeResponse` — unchanged shape, moved as-is.
  - `interface ImportedIngredientCandidate`, `interface ImportedIngredient`, `interface RecipeImportDraft` — unchanged shapes, moved as-is.
  - `interface RecipeFormValues { name: string; description: string; servings: string; imageUrl: string; sourceUrl: string; instructions: string; dietTags: string[]; isShared: boolean; ingredients: IngredientRow[]; }`
  - `interface RecipeSavePayload { name: string; description?: string; servings: number; image_url: string; source_url: string; instructions: string; diet_tags: string[]; is_shared: boolean; ingredients: Array<{ fdc_id?: number; food_name: string; brand_name?: string; amount_g: number; calories?: number; protein_g?: number; fat_g?: number; carbs_g?: number; fiber_g?: number; }>; }`
  - `function blankFormValues(): RecipeFormValues`
  - `function formValuesFromRecipe(recipe: RecipeResponse): RecipeFormValues`
  - `function formValuesFromDraft(draft: RecipeImportDraft): RecipeFormValues`
  - `export default function RecipeEditForm(props: RecipeEditFormProps): JSX.Element` where
    `interface RecipeEditFormProps { initialValues: RecipeFormValues; userProfile: any; onSave: (payload: RecipeSavePayload) => void | Promise<void>; submitLabel: string; savingLabel: string; saving: boolean; submitError?: string; submitMessage?: string; banner?: React.ReactNode; }`

**Why this task exists:** `RecipeBuilder.tsx` today has one edit form (name/description/servings/image/source/instructions/diet-tags/is_shared/ingredients-with-USDA-autocomplete) reused across its add/edit/import flows via direct `useState` calls. Task 5's bulk-import review queue needs that exact same editing UI, one draft at a time. Duplicating the ingredient-matching logic (autocomplete, portion lookups, the branded-food dedup fix from this session) would be real, error-prone duplication — so it moves into a shared component instead. This is a pure refactor: no behavior changes, verified by the existing test file passing before and after.

- [ ] **Step 1: Run the existing test file to confirm the baseline passes before touching anything**

Run: `cd pakupaku-frontend && CI=true npx --no-install react-scripts test --watchAll=false src/components/RecipeBuilder.test.tsx`
Expected: 4 tests pass (`importing a URL pre-fills the recipe form`, `branded-only search results with the same description collapse to one suggestion`, `is_shared checkbox only appears for admins`, `importing a URL carries instructions into the form`).

- [ ] **Step 2: Create `RecipeEditForm.tsx`**

```tsx
import { useState, useEffect, useRef } from "react";
import "./RecipeBuilder.css";
import { apiFetch } from "../apiBase";

// ─── Unit conversion ──────────────────────────────────────

const UNIT_TO_G: Record<string, number> = {
  g:    1,
  ml:   1,
  oz:   28.3495,
  cup:  240,
  tbsp: 15,
  tsp:  5,
  lb:   453.592,
  kg:   1000,
  l:    1000,
};
const STANDARD_UNITS = ["g", "ml", "oz", "cup", "tbsp", "tsp", "lb", "kg", "l"];
const STANDARD_UNIT_SET = new Set(STANDARD_UNITS);

/** Natural units are food-specific USDA portions that aren't in our standard list. */
function naturalUnits(portionsMap: Record<string, number>): string[] {
  return Object.keys(portionsMap).filter(u => !STANDARD_UNIT_SET.has(u));
}

// portionsMap overrides the generic table with food-specific gram weights from USDA
function toGrams(amount: string, unit: string, portionsMap: Record<string, number> = {}): number {
  const conv = { ...UNIT_TO_G, ...portionsMap };
  return (parseFloat(amount) || 0) * (conv[unit] ?? 1);
}

function scale(per100g: number | null, amount_g: number): number | undefined {
  if (per100g == null) return undefined;
  return (per100g * amount_g) / 100;
}

function rowKcal(row: { calories_per_100g: number | null; amount: string; unit: string; portionsMap: Record<string, number> }): number | null {
  if (row.calories_per_100g == null || !row.amount.trim()) return null;
  return (row.calories_per_100g * toGrams(row.amount, row.unit, row.portionsMap)) / 100;
}

// Label shown for a unit in the dropdown — adds gram weight when known and non-trivial
function unitLabel(unit: string, portionsMap: Record<string, number>): string {
  if (unit === "g" || unit === "ml") return unit;
  const g = portionsMap[unit] ?? UNIT_TO_G[unit];
  return g ? `${unit} (${Math.round(g)}g)` : unit;
}

// ─── USDA nutrient extraction ─────────────────────────────

interface NutrientData {
  calories_per_100g: number | null;
  protein_per_100g:  number | null;
  fat_per_100g:      number | null;
  carbs_per_100g:    number | null;
  fiber_per_100g:    number | null;
}

const NUTRIENT_ID_MAP: Record<number, keyof NutrientData> = {
  1008: "calories_per_100g",
  1003: "protein_per_100g",
  1004: "fat_per_100g",
  1005: "carbs_per_100g",
  1079: "fiber_per_100g",
};

// When no generic (Foundation/SR Legacy/Survey) result exists for a query,
// runSearch() falls back to branded results — which for a common ingredient
// like "gochujang" can mean five near-identical branded products cluttering
// the dropdown. Collapse them to one entry per unique description, keeping
// the first (USDA's own relevance-ranked order) match for each.
function dedupeByDescription(foods: any[]): any[] {
  const seen = new Set<string>();
  const out: any[] = [];
  for (const f of foods) {
    const key = String(f.description ?? "").trim().toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(f);
  }
  return out;
}

function extractNutrients(foodNutrients: any[]): NutrientData {
  const result: NutrientData = {
    calories_per_100g: null,
    protein_per_100g:  null,
    fat_per_100g:      null,
    carbs_per_100g:    null,
    fiber_per_100g:    null,
  };
  for (const n of foodNutrients) {
    const key = NUTRIENT_ID_MAP[n.nutrientId as number];
    if (key && n.value != null) result[key] = n.value;
  }
  return result;
}

// ─── Types ────────────────────────────────────────────────

interface FoodSuggestion extends NutrientData {
  fdc_id:      number;
  description: string;
  brand:       string | null;
}

export interface IngredientRow extends NutrientData {
  // input mode
  mode: "search" | "custom";

  // search UI state
  query:            string;
  suggestions:      FoodSuggestion[];
  showDropdown:     boolean;

  // brand UI state
  brandSuggestions: string[];
  showBrandDropdown: boolean;

  // resolved food
  fdc_id:    number | null;
  food_name: string;
  brand_name: string;

  // food-specific unit → grams from USDA (overrides generic UNIT_TO_G)
  portionsMap: Record<string, number>;

  // amount
  amount: string;
  unit:   string;
}

function blankRow(): IngredientRow {
  return {
    mode: "search",
    query: "", suggestions: [], showDropdown: false,
    brandSuggestions: [], showBrandDropdown: false,
    fdc_id: null, food_name: "", brand_name: "",
    calories_per_100g: null, protein_per_100g: null,
    fat_per_100g: null, carbs_per_100g: null, fiber_per_100g: null,
    portionsMap: {},
    amount: "", unit: "g",
  };
}

interface SavedIngredient {
  id:          string;
  fdc_id?:     number;
  food_name:   string;
  brand_name?: string;
  amount_g:    number;
  calories?:   number;
  protein_g?:  number;
  fat_g?:      number;
  carbs_g?:    number;
  fiber_g?:    number;
}

export interface RecipeResponse {
  id:              string;
  name:            string;
  description?:    string;
  servings:        number;
  total_calories?: number;
  total_protein_g?: number;
  total_fat_g?:    number;
  total_carbs_g?:  number;
  total_fiber_g?:  number;
  image_url?:    string | null;
  source_url?:   string | null;
  instructions?: string | null;
  diet_tags?:    string[];
  is_shared?:    boolean;
  ingredients: SavedIngredient[];
}

export interface ImportedIngredientCandidate extends NutrientData {
  fdc_id:      number;
  description: string;
  brand:       string | null;
  portions_map: Record<string, number>;
}

export interface ImportedIngredient {
  raw_line:   string;
  quantity:   number;
  unit:       string;
  food_name:  string;
  best_match: ImportedIngredientCandidate | null;
  alternates: ImportedIngredientCandidate[];
}

export interface RecipeImportDraft {
  name:        string;
  servings:    number;
  image_url:   string | null;
  ingredients: ImportedIngredient[];
  source_url:  string;
  instructions?: string | null;
}

function rowFromImportedIngredient(ing: ImportedIngredient): IngredientRow {
  const match = ing.best_match;
  return {
    mode: match ? "search" : "custom",
    query: match ? match.description : ing.food_name,
    suggestions: [], showDropdown: false,
    brandSuggestions: [], showBrandDropdown: false,
    fdc_id: match ? match.fdc_id : null,
    food_name: match ? match.description : ing.food_name,
    brand_name: match?.brand ?? "",
    calories_per_100g: match?.calories_per_100g ?? null,
    protein_per_100g:  match?.protein_per_100g  ?? null,
    fat_per_100g:      match?.fat_per_100g      ?? null,
    carbs_per_100g:    match?.carbs_per_100g    ?? null,
    fiber_per_100g:    match?.fiber_per_100g    ?? null,
    portionsMap: match?.portions_map ?? {},
    amount: String(ing.quantity),
    unit: ing.unit,
  };
}

export const DIET_TAGS = [
  "vegan", "vegetarian", "pescatarian", "flexitarian",
  "gluten_free", "dairy_free", "nut_free", "soy_free", "egg_free", "shellfish_free",
  "keto", "low_carb", "paleo", "whole30", "low_fodmap", "diabetic_friendly",
  "low_sodium", "low_fat", "high_protein",
  "halal", "kosher",
  "mediterranean", "dash",
];

function toggleDietTag(tags: string[], tag: string): string[] {
  return tags.includes(tag) ? tags.filter(t => t !== tag) : [...tags, tag];
}

// ─── Form value helpers ────────────────────────────────────

export interface RecipeFormValues {
  name: string;
  description: string;
  servings: string;
  imageUrl: string;
  sourceUrl: string;
  instructions: string;
  dietTags: string[];
  isShared: boolean;
  ingredients: IngredientRow[];
}

export function blankFormValues(): RecipeFormValues {
  return {
    name: "", description: "", servings: "1",
    imageUrl: "", sourceUrl: "", instructions: "",
    dietTags: [], isShared: false,
    ingredients: [blankRow()],
  };
}

export function formValuesFromRecipe(recipe: RecipeResponse): RecipeFormValues {
  // Nutrients are already per-amount_g in the DB, so we store them back
  // as per-100g by reversing.
  const rows: IngredientRow[] = recipe.ingredients.map(ing => {
    const isCustom = ing.fdc_id == null;
    const per100 = (v?: number) =>
      v != null && ing.amount_g > 0 ? (v / ing.amount_g) * 100 : null;
    return {
      mode:              isCustom ? "custom" : "search",
      query:             ing.food_name,
      suggestions:       [],
      showDropdown:      false,
      brandSuggestions:  [],
      showBrandDropdown: false,
      fdc_id:            ing.fdc_id ?? null,
      food_name:         ing.food_name,
      brand_name:        ing.brand_name ?? "",
      calories_per_100g: per100(ing.calories),
      protein_per_100g:  per100(ing.protein_g),
      fat_per_100g:      per100(ing.fat_g),
      carbs_per_100g:    per100(ing.carbs_g),
      fiber_per_100g:    per100(ing.fiber_g),
      portionsMap:       {},
      amount:            String(ing.amount_g),
      unit:              "g",
    };
  });
  return {
    name: recipe.name,
    description: recipe.description ?? "",
    servings: String(recipe.servings),
    imageUrl: recipe.image_url ?? "",
    sourceUrl: recipe.source_url ?? "",
    instructions: recipe.instructions ?? "",
    dietTags: recipe.diet_tags ?? [],
    isShared: recipe.is_shared ?? false,
    ingredients: rows.length > 0 ? rows : [blankRow()],
  };
}

export function formValuesFromDraft(draft: RecipeImportDraft): RecipeFormValues {
  return {
    name: draft.name,
    description: "",
    servings: String(draft.servings),
    imageUrl: draft.image_url ?? "",
    sourceUrl: draft.source_url ?? "",
    instructions: draft.instructions ?? "",
    dietTags: [],
    isShared: false,
    ingredients:
      draft.ingredients.length > 0
        ? draft.ingredients.map(rowFromImportedIngredient)
        : [blankRow()],
  };
}

export interface RecipeSavePayload {
  name: string;
  description?: string;
  servings: number;
  image_url: string;
  source_url: string;
  instructions: string;
  diet_tags: string[];
  is_shared: boolean;
  ingredients: Array<{
    fdc_id?: number;
    food_name: string;
    brand_name?: string;
    amount_g: number;
    calories?: number;
    protein_g?: number;
    fat_g?: number;
    carbs_g?: number;
    fiber_g?: number;
  }>;
}

// ─── Main component ───────────────────────────────────────

interface RecipeEditFormProps {
  initialValues: RecipeFormValues;
  userProfile: any;
  onSave: (payload: RecipeSavePayload) => void | Promise<void>;
  submitLabel: string;
  savingLabel: string;
  saving: boolean;
  submitError?: string;
  submitMessage?: string;
  banner?: React.ReactNode;
}

export default function RecipeEditForm({
  initialValues, userProfile, onSave, submitLabel, savingLabel, saving, submitError, submitMessage, banner,
}: RecipeEditFormProps) {
  const [name, setName]                 = useState(initialValues.name);
  const [description, setDescription]   = useState(initialValues.description);
  const [servings, setServings]         = useState(initialValues.servings);
  const [imageUrl, setImageUrl]         = useState(initialValues.imageUrl);
  const [sourceUrl, setSourceUrl]       = useState(initialValues.sourceUrl);
  const [instructions, setInstructions] = useState(initialValues.instructions);
  const [dietTags, setDietTags]         = useState<string[]>(initialValues.dietTags);
  const [isShared, setIsShared]         = useState(initialValues.isShared);
  const [ingredients, setIngredients]   = useState<IngredientRow[]>(initialValues.ingredients);
  const [validationError, setValidationError] = useState("");

  const updateRow = (index: number, patch: Partial<IngredientRow>) => {
    setIngredients(prev =>
      prev.map((row, i) => i === index ? { ...row, ...patch } : row)
    );
  };

  const addIngredient = () =>
    setIngredients(prev => [...prev, blankRow()]);

  const removeIngredient = (index: number) =>
    setIngredients(prev => prev.filter((_, i) => i !== index));

  const handleSubmit = () => {
    setValidationError("");

    if (!name.trim()) {
      setValidationError("Recipe name is required.");
      return;
    }

    const valid = ingredients.filter(r => r.food_name.trim() && r.amount.trim());
    if (valid.length === 0) {
      setValidationError("Add at least one ingredient with a name and amount.");
      return;
    }

    const payload: RecipeSavePayload = {
      name:         name.trim(),
      description:  description.trim() || undefined,
      servings:     parseFloat(servings) || 1,
      image_url:    imageUrl.trim(),
      source_url:   sourceUrl.trim(),
      instructions: instructions.trim(),
      diet_tags:    dietTags,
      is_shared:    isShared,
      ingredients: valid.map(r => {
        const amount_g = toGrams(r.amount, r.unit, r.portionsMap);
        return {
          fdc_id:     r.fdc_id ?? undefined,
          food_name:  r.food_name.trim(),
          brand_name: r.brand_name.trim() || undefined,
          amount_g,
          calories:   scale(r.calories_per_100g,  amount_g),
          protein_g:  scale(r.protein_per_100g,   amount_g),
          fat_g:      scale(r.fat_per_100g,        amount_g),
          carbs_g:    scale(r.carbs_per_100g,      amount_g),
          fiber_g:    scale(r.fiber_per_100g,      amount_g),
        };
      }),
    };

    onSave(payload);
  };

  return (
    <div className="recipe-form-card">
      {banner}
      <label className="recipe-field">
        <span>Name</span>
        <input type="text" value={name}
          onChange={e => setName(e.target.value)} placeholder="Recipe name" />
      </label>
      <label className="recipe-field">
        <span>Description</span>
        <textarea value={description}
          onChange={e => setDescription(e.target.value)}
          placeholder="Optional description" />
      </label>
      <label className="recipe-field recipe-field-inline">
        <span>Servings</span>
        <input type="number" min="1" step="0.5" value={servings}
          onChange={e => setServings(e.target.value)} />
      </label>
      <label className="recipe-field">
        <span>Image URL</span>
        <input type="url" value={imageUrl}
          onChange={e => setImageUrl(e.target.value)}
          placeholder="https://example.com/photo.jpg" />
      </label>
      <label className="recipe-field">
        <span>Source link</span>
        <input type="url" value={sourceUrl}
          onChange={e => setSourceUrl(e.target.value)}
          placeholder="https://example.com/original-recipe" />
      </label>
      <label className="recipe-field">
        <span>Instructions</span>
        <textarea value={instructions}
          onChange={e => setInstructions(e.target.value)}
          placeholder={"One step per line\ne.g.\nHeat the broth.\nSeason and serve."} />
      </label>
      <div className="recipe-field">
        <span>Diet tags</span>
        <div className="diet-tags-grid">
          {DIET_TAGS.map(tag => (
            <label key={tag} className="diet-tag-checkbox">
              <input
                type="checkbox"
                checked={dietTags.includes(tag)}
                onChange={() => setDietTags(prev => toggleDietTag(prev, tag))}
              />
              {tag.replace(/_/g, " ")}
            </label>
          ))}
        </div>
      </div>
      {userProfile?.is_admin && (
        <div className="recipe-field recipe-field-inline recipe-shared-toggle">
          <span>Share in the shared recipe library</span>
          <label className="toggle-switch">
            <input
              type="checkbox"
              checked={isShared}
              onChange={e => setIsShared(e.target.checked)}
            />
            <span className="toggle-track">
              <span className="toggle-thumb" />
            </span>
          </label>
        </div>
      )}

      <div className="ingredient-section">
        <div className="section-heading">
          <h2>Ingredients</h2>
          <button type="button" className="add-ingredient-button" onClick={addIngredient}>
            + Add ingredient
          </button>
        </div>

        <div className="ingredient-header">
          <span>food</span>
          <span>brand (optional)</span>
          <span>amount</span>
          <span>unit</span>
          <span>kcal</span>
          <span />
        </div>

        {ingredients.map((row, index) => (
          <IngredientInput
            key={index}
            row={row}
            onUpdate={patch => updateRow(index, patch)}
            onRemove={() => removeIngredient(index)}
          />
        ))}

        {(() => {
          const total = ingredients.reduce((sum, r) => {
            const k = rowKcal(r);
            return k != null ? sum + k : sum;
          }, 0);
          const svgs = parseFloat(servings) || 1;
          if (total === 0) return null;
          return (
            <div className="ingredient-kcal-total">
              <span>total</span>
              <span>{Math.round(total)} kcal</span>
              {svgs > 1 && (
                <span className="ingredient-kcal-per-serving">
                  ({Math.round(total / svgs)} kcal / serving)
                </span>
              )}
            </div>
          );
        })()}
      </div>

      {(validationError || submitError) && <p className="recipe-error">{validationError || submitError}</p>}
      {submitMessage && <p className="recipe-success">{submitMessage}</p>}
      <button type="button" className="save-recipe-button"
        onClick={handleSubmit} disabled={saving}>
        {saving ? savingLabel : submitLabel}
      </button>
    </div>
  );
}

// ─── Ingredient row with autocomplete ─────────────────────

interface IngredientInputProps {
  row:      IngredientRow;
  onUpdate: (patch: Partial<IngredientRow>) => void;
  onRemove: () => void;
}

function IngredientInput({ row, onUpdate, onRemove }: IngredientInputProps) {
  const wrapRef       = useRef<HTMLDivElement>(null);
  const debounceRef   = useRef<ReturnType<typeof setTimeout> | null>(null);
  const brandDebRef   = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Close both dropdowns on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        onUpdate({ showDropdown: false, showBrandDropdown: false });
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [onUpdate]);

  const runSearch = (query: string, brand: string) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (query.trim().length < 2) {
      onUpdate({ suggestions: [], showDropdown: false });
      return;
    }
    debounceRef.current = setTimeout(async () => {
      try {
        const token = localStorage.getItem("token");
        const hasBrand = brand.trim().length > 0;
        let url = `/foods/search?query=${encodeURIComponent(query.trim())}&page_size=50`;
        if (hasBrand) url += `&brand_owner=${encodeURIComponent(brand.trim())}`;
        const res = await apiFetch(url, { headers: { Authorization: token ? `Bearer ${token}` : "" } });
        if (!res.ok) return;
        const data = await res.json();

        // Prefer generic foods; fall back to branded if no generic results exist.
        // The branded fallback is deduped by description — with no brand filter
        // active, the user is picking "an ingredient", not "a specific product",
        // so five branded listings that all just say "Gochujang" collapse to one.
        // An explicit brand filter (hasBrand) is a deliberate narrowing to that
        // brand's own catalog, so its results are left exactly as returned.
        const all     = data.foods ?? [];
        const generic = all.filter((f: any) => f.dataType !== "Branded");
        const branded = all.filter((f: any) => f.dataType === "Branded");
        const pool    = hasBrand ? branded : (generic.length > 0 ? generic : dedupeByDescription(branded));

        const suggestions: FoodSuggestion[] = pool.map((f: any) => ({
          fdc_id:      f.fdcId,
          description: f.description,
          brand:       f.brandOwner || f.brandName || null,
          ...extractNutrients(f.foodNutrients ?? []),
        }));
        onUpdate({ suggestions, showDropdown: suggestions.length > 0 });
      } catch { /* silently ignore */ }
    }, 350);
  };

  const runBrandSearch = (brandText: string, foodQuery: string) => {
    if (brandDebRef.current) clearTimeout(brandDebRef.current);
    if (brandText.trim().length < 2) {
      onUpdate({ brandSuggestions: [], showBrandDropdown: false });
      return;
    }
    brandDebRef.current = setTimeout(async () => {
      try {
        const token = localStorage.getItem("token");
        // Use the food query if we have one, otherwise use the brand text as the query
        const q = foodQuery.trim().length >= 2 ? foodQuery.trim() : brandText.trim();
        const res = await apiFetch(
          `/foods/search?query=${encodeURIComponent(q)}&page_size=100`,
          { headers: { Authorization: token ? `Bearer ${token}` : "" } }
        );
        if (!res.ok) return;
        const data = await res.json();
        const lower = brandText.toLowerCase();
        const seen = new Set<string>();
        const brands: string[] = [];
        for (const f of data.foods ?? []) {
          if (f.dataType !== "Branded") continue;
          const b: string = f.brandOwner || f.brandName || "";
          if (!b || !b.toLowerCase().includes(lower) || seen.has(b)) continue;
          seen.add(b);
          brands.push(b);
          if (brands.length >= 8) break;
        }
        onUpdate({ brandSuggestions: brands, showBrandDropdown: brands.length > 0 });
      } catch { /* ignore */ }
    }, 350);
  };

  const handleQueryChange = (value: string) => {
    onUpdate({ query: value, food_name: value, fdc_id: null });
    runSearch(value, row.brand_name);
  };

  const handleBrandChange = (value: string) => {
    onUpdate({ brand_name: value, showBrandDropdown: false });
    runBrandSearch(value, row.query);
    if (row.query.trim().length >= 2) runSearch(row.query, value);
  };

  const selectBrand = (brand: string) => {
    onUpdate({ brand_name: brand, brandSuggestions: [], showBrandDropdown: false });
    if (row.query.trim().length >= 2) runSearch(row.query, brand);
  };

  const selectFood = async (food: FoodSuggestion) => {
    // Immediately fill what we already know from the search result
    onUpdate({
      query:             food.description,
      food_name:         food.description,
      brand_name:        food.brand ?? "",
      fdc_id:            food.fdc_id,
      calories_per_100g: food.calories_per_100g,
      protein_per_100g:  food.protein_per_100g,
      fat_per_100g:      food.fat_per_100g,
      carbs_per_100g:    food.carbs_per_100g,
      fiber_per_100g:    food.fiber_per_100g,
      suggestions:       [],
      showDropdown:      false,
    });

    // Fetch food-specific portion gram weights.
    //
    // Some USDA Foundation food records appear in search results but return
    // 404 from the detail endpoint (a known USDA data inconsistency).
    // When that happens we fall back to a targeted re-search filtered to
    // Survey (FNDDS) and SR Legacy, which reliably have portion data.

    const token = localStorage.getItem("token");
    const headers = { Authorization: token ? `Bearer ${token}` : "" };

    const fetchPortions = async (fdc_id: number): Promise<Record<string, number> | null> => {
      try {
        const res = await apiFetch(`/foods/${fdc_id}`, { headers });
        if (!res.ok) return null;
        const detail = await res.json();
        const map: Record<string, number> = {};
        for (const p of detail.portions ?? []) {
          if (p.unit && p.grams_per_unit) map[p.unit] = p.grams_per_unit;
        }
        return Object.keys(map).length > 0 ? map : null;
      } catch {
        return null;
      }
    };

    // Tier 1: try the selected food directly
    let portionsMap = await fetchPortions(food.fdc_id);

    // Tier 2: if that failed (e.g. Foundation 404), re-search the same
    // description and pick the first Survey/SR Legacy result, which reliably
    // have food portions. We avoid passing data_types= because parentheses
    // in "Survey (FNDDS)" cause a 400 from the USDA API.
    if (!portionsMap) {
      try {
        const q   = encodeURIComponent(food.description);
        const res = await apiFetch(
          `/foods/search?query=${q}&page_size=20`,
          { headers },
        );
        if (res.ok) {
          const data = await res.json();
          const RELIABLE = new Set(["Survey (FNDDS)", "SR Legacy"]);
          for (const f of (data.foods ?? [])) {
            if (!RELIABLE.has(f.dataType)) continue;
            portionsMap = await fetchPortions(f.fdcId);
            if (portionsMap) break;
          }
        }
      } catch {
        // Non-fatal — fall through to generic conversions
      }
    }

    if (portionsMap) {
      const natural = Object.keys(portionsMap).filter(u => !STANDARD_UNIT_SET.has(u));
      const patch: Partial<IngredientRow> = { portionsMap };
      if (natural.length > 0) {
        patch.unit = natural[0];
        if (!row.amount.trim()) patch.amount = "1";
      }
      onUpdate(patch);
    }
  };

  const isCustom = row.mode === "custom";
  const knownUnits = new Set(STANDARD_UNITS);
  if (!isCustom) naturalUnits(row.portionsMap).forEach(u => knownUnits.add(u));

  return (
    <div className={`ingredient-row${isCustom ? " ingredient-row--custom" : ""}`} ref={wrapRef}>
      {/* Food: search autocomplete OR plain text for custom */}
      <div className="ingredient-search-wrap">
        {isCustom ? (
          <input
            type="text"
            className="ingredient-input"
            placeholder="Food name…"
            value={row.food_name}
            onChange={e => onUpdate({ food_name: e.target.value, query: e.target.value })}
          />
        ) : (
          <>
            <input
              type="text"
              className="ingredient-input"
              placeholder="Search food…"
              value={row.query}
              onChange={e => handleQueryChange(e.target.value)}
              onFocus={() => row.suggestions.length > 0 && onUpdate({ showDropdown: true })}
              autoComplete="off"
            />
            {row.showDropdown && (
              <ul className="autocomplete-dropdown">
                {row.suggestions.map(food => (
                  <li
                    key={food.fdc_id}
                    className="autocomplete-item"
                    onMouseDown={e => { e.preventDefault(); selectFood(food); }}
                  >
                    <span className="autocomplete-name">{food.description}</span>
                    {food.brand && <span className="autocomplete-brand">{food.brand}</span>}
                    {food.calories_per_100g != null && (
                      <span className="autocomplete-kcal">
                        {Math.round(food.calories_per_100g)} kcal/100g
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
        <button
          type="button"
          className="ingredient-mode-toggle"
          onClick={() => onUpdate(isCustom
            ? { mode: "search", food_name: "", query: "", fdc_id: null,
                calories_per_100g: null, protein_per_100g: null,
                fat_per_100g: null, carbs_per_100g: null, fiber_per_100g: null }
            : { mode: "custom", suggestions: [], showDropdown: false, fdc_id: null,
                portionsMap: {} }
          )}
        >
          {isCustom ? "↩ search USDA" : "enter manually"}
        </button>
      </div>

      {/* Brand — autocomplete in search mode, plain text in custom mode */}
      <div className="ingredient-brand-wrap">
        <input
          type="text"
          className="ingredient-input"
          placeholder={isCustom ? "Brand (optional)" : "Brand (optional)"}
          value={row.brand_name}
          onChange={e => isCustom
            ? onUpdate({ brand_name: e.target.value })
            : handleBrandChange(e.target.value)
          }
          onFocus={() => !isCustom && row.brandSuggestions.length > 0 && onUpdate({ showBrandDropdown: true })}
          autoComplete="off"
        />
        {!isCustom && row.showBrandDropdown && row.brandSuggestions.length > 0 && (
          <ul className="brand-autocomplete-dropdown">
            {row.brandSuggestions.map(brand => (
              <li
                key={brand}
                className="brand-autocomplete-item"
                onMouseDown={e => { e.preventDefault(); selectBrand(brand); }}
              >
                {brand}
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Amount */}
      <input
        type="number"
        className="ingredient-input ingredient-amount"
        placeholder="Amount"
        min="0"
        step="any"
        value={row.amount}
        onChange={e => onUpdate({ amount: e.target.value })}
      />

      {/* Unit */}
      <select
        className="ingredient-unit-select"
        value={row.unit}
        onChange={e => onUpdate({ unit: e.target.value })}
      >
        {!isCustom && naturalUnits(row.portionsMap).map(u => (
          <option key={u} value={u}>{unitLabel(u, row.portionsMap)}</option>
        ))}
        {!isCustom && naturalUnits(row.portionsMap).length > 0 && (
          <option disabled>──────</option>
        )}
        {STANDARD_UNITS.map(u => (
          <option key={u} value={u}>{unitLabel(u, row.portionsMap)}</option>
        ))}
        {!knownUnits.has(row.unit) && (
          <option value={row.unit}>{row.unit}</option>
        )}
      </select>

      {/* Kcal for this ingredient */}
      <div className="ingredient-kcal-cell">
        {(() => {
          const k = rowKcal(row);
          return k != null ? <span>{Math.round(k)}</span> : <span className="ingredient-kcal-empty">—</span>;
        })()}
      </div>

      <button
        type="button"
        className="remove-ingredient-button"
        onClick={onRemove}
        aria-label="Remove ingredient"
      >
        ×
      </button>

      {/* Custom nutrition fields — spans all columns */}
      {isCustom && (
        <div className="ingredient-custom-nutrition">
          <label className="custom-macro-field">
            <span>kcal / 100g</span>
            <input
              type="number" min="0" step="any" placeholder="0"
              value={row.calories_per_100g ?? ""}
              onChange={e => onUpdate({ calories_per_100g: e.target.value === "" ? null : parseFloat(e.target.value) })}
            />
          </label>
          <label className="custom-macro-field">
            <span>protein g / 100g</span>
            <input
              type="number" min="0" step="any" placeholder="0"
              value={row.protein_per_100g ?? ""}
              onChange={e => onUpdate({ protein_per_100g: e.target.value === "" ? null : parseFloat(e.target.value) })}
            />
          </label>
          <label className="custom-macro-field">
            <span>carbs g / 100g</span>
            <input
              type="number" min="0" step="any" placeholder="0"
              value={row.carbs_per_100g ?? ""}
              onChange={e => onUpdate({ carbs_per_100g: e.target.value === "" ? null : parseFloat(e.target.value) })}
            />
          </label>
          <label className="custom-macro-field">
            <span>fat g / 100g</span>
            <input
              type="number" min="0" step="any" placeholder="0"
              value={row.fat_per_100g ?? ""}
              onChange={e => onUpdate({ fat_per_100g: e.target.value === "" ? null : parseFloat(e.target.value) })}
            />
          </label>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Rewrite `RecipeBuilder.tsx` to use `RecipeEditForm`**

```tsx
import { useState, useEffect } from "react";
import "./RecipeBuilder.css";
import { apiFetch } from "../apiBase";
import RecipeEditForm, {
  RecipeResponse, RecipeImportDraft, RecipeFormValues, RecipeSavePayload,
  blankFormValues, formValuesFromRecipe, formValuesFromDraft,
} from "./RecipeEditForm";

interface RecipeBuilderProps {
  onBack: () => void;
  userProfile: any;
}

export default function RecipeBuilder({ onBack, userProfile }: RecipeBuilderProps) {
  const [recipes, setRecipes]       = useState<RecipeResponse[]>([]);
  const [loading, setLoading]       = useState(false);
  const [message, setMessage]       = useState("");
  const [error, setError]           = useState("");
  const [editingId, setEditingId]   = useState<string | null>(null);
  const [importUrl, setImportUrl]           = useState("");
  const [importing, setImporting]           = useState(false);
  const [importImageUrl, setImportImageUrl] = useState<string | null>(null);
  const [formValues, setFormValues] = useState<RecipeFormValues>(blankFormValues());
  const [formKey, setFormKey]       = useState(0);

  const fetchRecipes = async () => {
    try {
      const token = localStorage.getItem("token");
      const res = await apiFetch("/recipes", {
        headers: { Authorization: token ? `Bearer ${token}` : "" },
      });
      if (!res.ok) throw new Error("Could not load recipes.");
      setRecipes(await res.json());
    } catch {
      setError("Unable to load saved recipes.");
    }
  };

  useEffect(() => { fetchRecipes(); }, []);

  const startEdit = (recipe: RecipeResponse) => {
    setEditingId(recipe.id);
    setFormValues(formValuesFromRecipe(recipe));
    setFormKey(k => k + 1);
    setError("");
    setMessage("");
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const cancelEdit = () => {
    setEditingId(null);
    setFormValues(blankFormValues());
    setFormKey(k => k + 1);
    setImportImageUrl(null);
    setError("");
    setMessage("");
  };

  const startImport = async () => {
    if (!importUrl.trim()) {
      setError("Enter a recipe URL to import.");
      return;
    }
    setError(""); setMessage(""); setImporting(true);
    try {
      const token = localStorage.getItem("token");
      const res = await apiFetch("/recipes/import", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: token ? `Bearer ${token}` : "",
        },
        body: JSON.stringify({ url: importUrl.trim() }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail || "Couldn't import that recipe.");
      }
      const draft: RecipeImportDraft = await res.json();

      setEditingId(null);
      setFormValues(formValuesFromDraft(draft));
      setFormKey(k => k + 1);
      setImportImageUrl(draft.image_url);
      setImportUrl("");
      setMessage("Recipe imported — review the ingredients below, then save.");
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (err: any) {
      setError(err.message || "Unable to import that recipe.");
    } finally {
      setImporting(false);
    }
  };

  const handleFormSave = async (payload: RecipeSavePayload) => {
    setError("");
    setMessage("");
    setLoading(true);
    try {
      const token = localStorage.getItem("token");
      const isEdit = editingId !== null;
      const url    = isEdit ? `/recipes/${editingId}` : "/recipes";
      const method = isEdit ? "PATCH" : "POST";

      const res = await apiFetch(url, {
        method,
        headers: {
          "Content-Type": "application/json",
          Authorization: token ? `Bearer ${token}` : "",
        },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail || "Failed to save recipe.");
      }

      const saved = await res.json();
      setRecipes(prev =>
        isEdit
          ? prev.map(r => r.id === saved.id ? saved : r)
          : [saved, ...prev]
      );
      setMessage(isEdit ? "Recipe updated!" : "Recipe saved!");
      setEditingId(null);
      setFormValues(blankFormValues());
      setFormKey(k => k + 1);
      setImportImageUrl(null);
    } catch (err: any) {
      setError(err.message || "Unable to save recipe.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="recipe-builder-root">
      <div className="recipe-builder-container">
        <header className="recipe-builder-header">
          <button type="button" className="back-button" onClick={onBack}>← Back</button>
          <div>
            <h1 className="recipe-builder-title">Create a meal or recipe</h1>
            <p className="recipe-builder-subtitle">Combine ingredients and save recipes to your account.</p>
          </div>
        </header>

        <section className="recipe-form-section">
          <div className="recipe-form-card">
            <label className="recipe-field">
              <span>Import from a recipe blog URL</span>
              <div className="recipe-import-controls">
                <input
                  type="url"
                  value={importUrl}
                  onChange={e => setImportUrl(e.target.value)}
                  placeholder="https://example.com/some-recipe"
                />
                <button
                  type="button"
                  className="add-ingredient-button"
                  onClick={startImport}
                  disabled={importing}
                >
                  {importing ? "Importing…" : "Import"}
                </button>
              </div>
            </label>
            {importImageUrl && (
              <img src={importImageUrl} alt="" className="recipe-import-image" />
            )}
          </div>
        </section>

        <section className="recipe-form-section">
          <RecipeEditForm
            key={formKey}
            initialValues={formValues}
            userProfile={userProfile}
            onSave={handleFormSave}
            submitLabel={editingId ? "Update recipe" : "Save recipe"}
            savingLabel="Saving..."
            saving={loading}
            submitError={error}
            submitMessage={message}
            banner={editingId ? (
              <div className="recipe-edit-banner">
                <span>Editing recipe</span>
                <button type="button" className="cancel-edit-button" onClick={cancelEdit}>
                  Cancel
                </button>
              </div>
            ) : undefined}
          />
        </section>

        <section className="saved-recipes-section">
          <h2 className="section-title">Saved recipes</h2>
          {recipes.length === 0 ? (
            <div className="empty-state">No recipes yet. Save one to see it here.</div>
          ) : (
            <div className="saved-recipes-grid">
              {recipes.map(recipe => (
                <div key={recipe.id} className={`saved-recipe-card${editingId === recipe.id ? " saved-recipe-card--editing" : ""}`}>
                  <div className="saved-recipe-header">
                    <h3>{recipe.name}</h3>
                    <span>{recipe.servings} serving{recipe.servings !== 1 ? "s" : ""}</span>
                  </div>
                  {recipe.description && <p>{recipe.description}</p>}
                  {recipe.image_url && (
                    <img src={recipe.image_url} alt="" className="saved-recipe-image" />
                  )}
                  {recipe.diet_tags && recipe.diet_tags.length > 0 && (
                    <div className="saved-recipe-tags">
                      {recipe.diet_tags.map(tag => (
                        <span key={tag} className="diet-tag-pill">{tag.replace(/_/g, " ")}</span>
                      ))}
                    </div>
                  )}
                  {recipe.instructions && (
                    <ol className="saved-recipe-instructions">
                      {recipe.instructions.split("\n").filter(Boolean).map((step, i) => (
                        <li key={i}>{step}</li>
                      ))}
                    </ol>
                  )}
                  {recipe.source_url && (
                    <a href={recipe.source_url} target="_blank" rel="noreferrer" className="saved-recipe-source-link">
                      View original
                    </a>
                  )}
                  <div className="saved-recipe-stats">
                    <span>{recipe.total_calories != null ? Math.round(recipe.total_calories) : "—"} cal</span>
                    <span>{recipe.total_protein_g != null ? Math.round(recipe.total_protein_g) : "—"}g P</span>
                    <span>{recipe.total_carbs_g != null ? Math.round(recipe.total_carbs_g) : "—"}g C</span>
                    <span>{recipe.total_fat_g != null ? Math.round(recipe.total_fat_g) : "—"}g F</span>
                  </div>
                  <button
                    type="button"
                    className="edit-recipe-button"
                    onClick={() => startEdit(recipe)}
                    disabled={editingId === recipe.id}
                  >
                    {editingId === recipe.id ? "Editing…" : "Edit"}
                  </button>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run the existing test file again to confirm it still passes unchanged**

Run: `cd pakupaku-frontend && CI=true npx --no-install react-scripts test --watchAll=false src/components/RecipeBuilder.test.tsx`
Expected: same 4 tests pass, unchanged. This is the refactor's regression check — no new test is added for this task.

- [ ] **Step 5: Run the full frontend build to confirm the split compiles clean**

Run: `cd pakupaku-frontend && CI=true npm run build`
Expected: `Compiled successfully.`

- [ ] **Step 6: Commit**

```bash
git add pakupaku-frontend/src/components/RecipeEditForm.tsx pakupaku-frontend/src/components/RecipeBuilder.tsx
git commit -m "refactor: extract RecipeEditForm from RecipeBuilder"
```

---

### Task 2: Link discovery (`discover_recipe_links`)

**Files:**
- Create: `recipe_bulk_import.py`
- Create: `tests/fixtures/blog_index_page.html`
- Test: `tests/test_recipe_bulk_import_discovery.py`

**Interfaces:**
- Consumes: `fetch_page(url: str) -> str` and `HTTPException` from `recipe_import.py` (unchanged).
- Produces: `async def discover_recipe_links(index_url: str) -> List[str]`, consumed by Task 4's route.

- [ ] **Step 1: Create the fixture HTML**

```html
<html>
<body>
<nav>
  <a href="/category/desserts/">Desserts</a>
  <a href="/tag/vegan/">Vegan</a>
  <a href="/author/jane/">Jane</a>
</nav>
<main>
  <article>
    <a href="/recipes/chocolate-cake/">Chocolate Cake</a>
    <a href="/recipes/chocolate-cake/">Read more</a>
  </article>
  <article>
    <a href="https://recipeblog.example.com/recipes/banana-bread/">Banana Bread</a>
  </article>
  <article>
    <a href="/recipes/garlic-soup">Garlic Soup</a>
  </article>
  <a href="https://otherdomain.example.com/some-post/">An unrelated post on another site</a>
  <a href="/images/hero.jpg">Hero image</a>
  <a href="/page/2/">Next page</a>
  <a href="#top">Back to top</a>
  <a href="/search?q=cake">Search</a>
</main>
</body>
</html>
```

Save this to `tests/fixtures/blog_index_page.html`.

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_recipe_bulk_import_discovery.py
from pathlib import Path

import recipe_bulk_import
from recipe_bulk_import import discover_recipe_links

FIXTURES = Path(__file__).parent / "fixtures"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text()


async def test_discover_recipe_links_filters_and_dedupes(monkeypatch):
    async def fake_fetch_page(url):
        assert url == "https://recipeblog.example.com/category/desserts/"
        return _read("blog_index_page.html")

    monkeypatch.setattr(recipe_bulk_import, "fetch_page", fake_fetch_page)

    result = await discover_recipe_links("https://recipeblog.example.com/category/desserts/")

    assert result == [
        "https://recipeblog.example.com/recipes/chocolate-cake/",
        "https://recipeblog.example.com/recipes/banana-bread/",
        "https://recipeblog.example.com/recipes/garlic-soup",
    ]


async def test_discover_recipe_links_returns_empty_list_when_none_found(monkeypatch):
    async def fake_fetch_page(url):
        return "<html><body><p>No links here.</p></body></html>"

    monkeypatch.setattr(recipe_bulk_import, "fetch_page", fake_fetch_page)

    result = await discover_recipe_links("https://example.com/index/")
    assert result == []
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `pytest tests/test_recipe_bulk_import_discovery.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'recipe_bulk_import'`

- [ ] **Step 4: Create `recipe_bulk_import.py` with the discovery function**

```python
"""
recipe_bulk_import.py
----------------------
Bulk recipe import: given a blog index/archive URL, discover the
individual recipe post links on it and run recipe_import.py's existing
per-URL extraction pipeline over each one. Nothing is saved here —
callers get back a list of RecipeImportDraft objects for review, same
as a single import.
"""

import asyncio
import logging
from typing import List, Optional
from urllib.parse import urljoin, urlparse
import re

from bs4 import BeautifulSoup
from fastapi import HTTPException

from recipe_import import build_import_draft, fetch_page
from schemas import RecipeImportDraft

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  LINK DISCOVERY
# ─────────────────────────────────────────────

# Common non-post URL shapes on blog platforms. Deliberately conservative:
# a link that slips through this filter costs nothing, since
# bulk_extract_drafts() below treats "no recipe found" as a normal,
# silently-dropped outcome. A link wrongly excluded here is a real recipe
# that never gets a chance — worse, so the list stays short.
_EXCLUDED_PATH_PATTERNS = [
    re.compile(r"/tag/", re.IGNORECASE),
    re.compile(r"/category/", re.IGNORECASE),
    re.compile(r"/author/", re.IGNORECASE),
    re.compile(r"/page/\d+", re.IGNORECASE),
    re.compile(r"/search", re.IGNORECASE),
]
_EXCLUDED_EXTENSIONS = (
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg",
    ".pdf", ".xml", ".css", ".js", ".ico",
)


def _is_excluded_path(path: str) -> bool:
    lowered = path.lower()
    if lowered.endswith(_EXCLUDED_EXTENSIONS):
        return True
    return any(p.search(lowered) for p in _EXCLUDED_PATH_PATTERNS)


async def discover_recipe_links(index_url: str) -> List[str]:
    """Fetch index_url and return same-domain links that look like
    individual post pages: not the index page itself, not a bare
    fragment, not a tag/category/author/pagination/search URL, not a
    non-HTML file, and not cross-domain. Deduped, in first-seen order.

    This is a permissive heuristic, not a recipe classifier — pages that
    slip through get filtered for real by bulk_extract_drafts(), which
    only keeps URLs where build_import_draft() actually found a recipe.
    """
    html = await fetch_page(index_url)
    soup = BeautifulSoup(html, "html.parser")
    base_host = urlparse(index_url).hostname
    normalized_index = index_url.split("#")[0]

    seen = set()
    candidates: List[str] = []
    for tag in soup.find_all("a", href=True):
        href = tag["href"].strip()
        if not href or href.startswith("#"):
            continue

        absolute = urljoin(index_url, href)
        normalized = absolute.split("#")[0]
        if not normalized or normalized == normalized_index:
            continue

        parsed = urlparse(normalized)
        if parsed.scheme not in ("http", "https"):
            continue
        if parsed.hostname != base_host:
            continue
        if _is_excluded_path(parsed.path):
            continue
        if normalized in seen:
            continue

        seen.add(normalized)
        candidates.append(normalized)

    return candidates
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/test_recipe_bulk_import_discovery.py -v`
Expected: PASS (both tests)

- [ ] **Step 6: Commit**

```bash
git add recipe_bulk_import.py tests/fixtures/blog_index_page.html tests/test_recipe_bulk_import_discovery.py
git commit -m "feat: add recipe link discovery for bulk import"
```

---

### Task 3: Batch extraction (`bulk_extract_drafts`)

**Files:**
- Modify: `recipe_bulk_import.py` (add to the file created in Task 2)
- Test: `tests/test_recipe_bulk_import_extraction.py`

**Interfaces:**
- Consumes: `build_import_draft(url: str) -> RecipeImportDraft` from `recipe_import.py` (unchanged); `RecipeImportDraft` from `schemas.py`.
- Produces: `async def bulk_extract_drafts(urls: List[str]) -> List[RecipeImportDraft]`, consumed by Task 4's route.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_recipe_bulk_import_extraction.py
import asyncio

from fastapi import HTTPException

import recipe_bulk_import
from recipe_bulk_import import bulk_extract_drafts
from schemas import RecipeImportDraft


async def test_bulk_extract_drafts_drops_failures_and_keeps_successes(monkeypatch):
    calls = []

    async def fake_build_import_draft(url):
        calls.append(url)
        if url == "https://example.com/good-1":
            return RecipeImportDraft(
                name="Good One", servings=2.0, image_url=None,
                ingredients=[], source_url=url,
            )
        if url == "https://example.com/good-2":
            return RecipeImportDraft(
                name="Good Two", servings=1.0, image_url=None,
                ingredients=[], source_url=url,
            )
        raise HTTPException(status_code=422, detail="Couldn't find a recipe on that page.")

    monkeypatch.setattr(recipe_bulk_import, "build_import_draft", fake_build_import_draft)

    result = await bulk_extract_drafts([
        "https://example.com/good-1",
        "https://example.com/bad",
        "https://example.com/good-2",
    ])

    assert sorted(calls) == sorted([
        "https://example.com/good-1", "https://example.com/bad", "https://example.com/good-2",
    ])
    assert sorted(d.name for d in result) == ["Good One", "Good Two"]


async def test_bulk_extract_drafts_bounds_concurrency(monkeypatch):
    in_flight = 0
    max_in_flight = 0
    lock = asyncio.Lock()

    async def fake_build_import_draft(url):
        nonlocal in_flight, max_in_flight
        async with lock:
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
        await asyncio.sleep(0.01)
        async with lock:
            in_flight -= 1
        return RecipeImportDraft(
            name=url, servings=1.0, image_url=None, ingredients=[], source_url=url,
        )

    monkeypatch.setattr(recipe_bulk_import, "build_import_draft", fake_build_import_draft)

    urls = [f"https://example.com/post-{i}" for i in range(20)]
    result = await bulk_extract_drafts(urls)

    assert len(result) == 20
    assert max_in_flight <= 5
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_recipe_bulk_import_extraction.py -v`
Expected: FAIL with `AttributeError: module 'recipe_bulk_import' has no attribute 'bulk_extract_drafts'`

- [ ] **Step 3: Add `bulk_extract_drafts` to `recipe_bulk_import.py`**

Append to the end of `recipe_bulk_import.py`:

```python

# ─────────────────────────────────────────────
#  BATCH EXTRACTION
# ─────────────────────────────────────────────

_MAX_CONCURRENT_EXTRACTIONS = 5


async def _safe_build_import_draft(
    url: str, semaphore: asyncio.Semaphore
) -> Optional[RecipeImportDraft]:
    async with semaphore:
        try:
            return await build_import_draft(url)
        except HTTPException:
            return None
        except Exception:
            logger.exception(
                "bulk_extract_drafts: unexpected failure extracting %r", url
            )
            return None


async def bulk_extract_drafts(urls: List[str]) -> List[RecipeImportDraft]:
    """Run build_import_draft() over every URL, concurrency-bounded to
    _MAX_CONCURRENT_EXTRACTIONS in-flight extractions so a large batch
    can't hammer the source site or the LLM endpoint all at once. URLs
    where extraction fails (no recipe found, fetch error, anything
    build_import_draft raises HTTPException for) are silently dropped —
    mirrors recipe_import.py's _safe_match_ingredient, so one bad URL in
    a batch can't sink the whole run."""
    semaphore = asyncio.Semaphore(_MAX_CONCURRENT_EXTRACTIONS)
    results = await asyncio.gather(
        *(_safe_build_import_draft(url, semaphore) for url in urls)
    )
    return [draft for draft in results if draft is not None]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_recipe_bulk_import_extraction.py -v`
Expected: PASS (both tests)

- [ ] **Step 5: Run the full backend test suite to confirm nothing else broke**

Run: `pytest -v`
Expected: all tests pass, including the new discovery and extraction tests from Task 2.

- [ ] **Step 6: Commit**

```bash
git add recipe_bulk_import.py tests/test_recipe_bulk_import_extraction.py
git commit -m "feat: add concurrency-bounded batch extraction for bulk import"
```

---

### Task 4: Bulk-import routes

**Files:**
- Modify: `schemas.py`
- Modify: `main.py`
- Test: `tests/test_bulk_recipe_import_routes.py`

**Interfaces:**
- Consumes: `discover_recipe_links(index_url: str) -> List[str]` and `bulk_extract_drafts(urls: List[str]) -> List[RecipeImportDraft]` from `recipe_bulk_import.py` (Tasks 2 and 3); `User.is_admin` (existing field); `get_current_user` (existing dependency).
- Produces: `POST /recipes/bulk-import/discover` and `POST /recipes/bulk-import/extract` routes, consumed by Task 5's frontend.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_bulk_recipe_import_routes.py
import asyncio
import uuid

from auth import get_current_user, hash_password
from database import get_db
from main import app
from models import User
import main


async def _make_user(db_session, *, is_admin=False, email=None):
    user = User(
        id=uuid.uuid4(),
        email=email or f"{uuid.uuid4()}@example.com",
        username=f"user{uuid.uuid4().hex[:8]}",
        hashed_password=hash_password("TestPass123!"),
        email_verified=True,
        safe_mode=False,
        uses_custom_goals=False,
        is_admin=is_admin,
    )
    db_session.add(user)
    await db_session.flush()
    return user


def _as(client, user):
    app.dependency_overrides[get_current_user] = lambda: user
    return client


def test_discover_requires_admin(client, db_session):
    user = asyncio.get_event_loop().run_until_complete(_make_user(db_session))
    try:
        res = _as(client, user).post(
            "/recipes/bulk-import/discover", json={"url": "https://example.com/blog"}
        )
        assert res.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_discover_returns_links_for_admin(client, db_session, monkeypatch):
    admin = asyncio.get_event_loop().run_until_complete(
        _make_user(db_session, is_admin=True)
    )

    async def fake_discover(url):
        assert url == "https://example.com/blog"
        return ["https://example.com/blog/recipe-1", "https://example.com/blog/recipe-2"]

    monkeypatch.setattr(main, "discover_recipe_links", fake_discover)
    try:
        res = _as(client, admin).post(
            "/recipes/bulk-import/discover", json={"url": "https://example.com/blog"}
        )
        assert res.status_code == 200
        assert res.json()["urls"] == [
            "https://example.com/blog/recipe-1", "https://example.com/blog/recipe-2",
        ]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_extract_requires_admin(client, db_session):
    user = asyncio.get_event_loop().run_until_complete(_make_user(db_session))
    try:
        res = _as(client, user).post(
            "/recipes/bulk-import/extract", json={"urls": ["https://example.com/a"]}
        )
        assert res.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_extract_returns_drafts_for_admin(client, db_session, monkeypatch):
    from schemas import RecipeImportDraft

    admin = asyncio.get_event_loop().run_until_complete(
        _make_user(db_session, is_admin=True)
    )

    async def fake_extract(urls):
        assert urls == ["https://example.com/a", "https://example.com/b"]
        return [
            RecipeImportDraft(
                name="A", servings=1.0, image_url=None,
                ingredients=[], source_url="https://example.com/a",
            ),
        ]

    monkeypatch.setattr(main, "bulk_extract_drafts", fake_extract)
    try:
        res = _as(client, admin).post(
            "/recipes/bulk-import/extract",
            json={"urls": ["https://example.com/a", "https://example.com/b"]},
        )
        assert res.status_code == 200
        drafts = res.json()["drafts"]
        assert len(drafts) == 1
        assert drafts[0]["name"] == "A"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_extract_empty_result_when_nothing_found(client, db_session, monkeypatch):
    admin = asyncio.get_event_loop().run_until_complete(
        _make_user(db_session, is_admin=True)
    )

    async def fake_extract(urls):
        return []

    monkeypatch.setattr(main, "bulk_extract_drafts", fake_extract)
    try:
        res = _as(client, admin).post(
            "/recipes/bulk-import/extract", json={"urls": ["https://example.com/a"]}
        )
        assert res.status_code == 200
        assert res.json()["drafts"] == []
    finally:
        app.dependency_overrides.pop(get_current_user, None)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_bulk_recipe_import_routes.py -v`
Expected: FAIL — the routes don't exist yet (404s instead of the expected status codes).

- [ ] **Step 3: Add the new schemas**

In `schemas.py`, immediately after the `RecipeImportDraft` class (the end of the "RECIPE IMPORT" section), add:

```python


class BulkDiscoverRequest(BaseModel):
    url: str


class BulkDiscoverResponse(BaseModel):
    urls: List[str]


class BulkExtractRequest(BaseModel):
    urls: List[str]


class BulkExtractResponse(BaseModel):
    drafts: List[RecipeImportDraft]
```

- [ ] **Step 4: Add the import and the two routes to `main.py`**

Add to the import block near the top of `main.py`, right after the existing `from recipe_import import build_import_draft` line:

```python
from recipe_bulk_import import discover_recipe_links, bulk_extract_drafts
```

Add `BulkDiscoverRequest, BulkDiscoverResponse, BulkExtractRequest, BulkExtractResponse` to the existing `from schemas import (...)` block (alongside `RecipeImportDraft`).

Add the two routes immediately after `import_recipe` (right before `@app.get("/recipes", ...)`):

```python
@app.post("/recipes/bulk-import/discover", response_model=BulkDiscoverResponse)
async def bulk_import_discover(
    payload:      BulkDiscoverRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Fetch a blog index/archive URL and return the same-domain links on it
    that look like individual recipe posts. Nothing is fetched beyond
    this one page — the frontend shows the count and asks the admin to
    confirm before POST /recipes/bulk-import/extract actually runs the
    (potentially slow) extraction pass over them.
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required.")
    urls = await discover_recipe_links(payload.url)
    return BulkDiscoverResponse(urls=urls)


@app.post("/recipes/bulk-import/extract", response_model=BulkExtractResponse)
async def bulk_import_extract(
    payload:      BulkExtractRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Run the same extraction pipeline as POST /recipes/import over every
    URL in payload.urls, concurrency-bounded. URLs with no recipe found
    are silently dropped. Nothing is saved — the frontend opens the
    resulting drafts in a one-at-a-time review queue before calling
    POST /recipes for each one the admin keeps.
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required.")
    drafts = await bulk_extract_drafts(payload.urls)
    return BulkExtractResponse(drafts=drafts)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/test_bulk_recipe_import_routes.py -v`
Expected: PASS (all 5 tests)

- [ ] **Step 6: Run the full backend test suite**

Run: `pytest -v`
Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add schemas.py main.py tests/test_bulk_recipe_import_routes.py
git commit -m "feat: add admin-gated bulk recipe import routes"
```

---

### Task 5: `BulkRecipeImport.tsx` frontend screen

**Files:**
- Create: `pakupaku-frontend/src/components/BulkRecipeImport.tsx`
- Create: `pakupaku-frontend/src/components/BulkRecipeImport.css`
- Test: `pakupaku-frontend/src/components/BulkRecipeImport.test.tsx`

**Interfaces:**
- Consumes: `RecipeEditForm` (default export), `RecipeImportDraft`, `RecipeSavePayload`, `formValuesFromDraft` (named exports) from `./RecipeEditForm` (Task 1); `POST /recipes/bulk-import/discover`, `POST /recipes/bulk-import/extract`, `POST /recipes` (Task 4 and pre-existing) via `apiFetch`.
- Produces: `export default function BulkRecipeImport({ onBack, userProfile }: { onBack: () => void; userProfile: any }): JSX.Element`, consumed by Task 6's `App.tsx`.

- [ ] **Step 1: Write the failing tests**

```tsx
// pakupaku-frontend/src/components/BulkRecipeImport.test.tsx
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import BulkRecipeImport from "./BulkRecipeImport";

const draftA = {
  name: "Chocolate Cake",
  servings: 8,
  image_url: null,
  source_url: "https://example.com/recipes/chocolate-cake/",
  instructions: "Mix. Bake.",
  ingredients: [
    {
      raw_line: "2 cups flour",
      quantity: 2,
      unit: "cup",
      food_name: "flour",
      best_match: {
        fdc_id: 111,
        description: "Flour, wheat, all-purpose",
        brand: null,
        calories_per_100g: 364,
        protein_per_100g: 10,
        fat_per_100g: 1,
        carbs_per_100g: 76,
        fiber_per_100g: 2.7,
        portions_map: {},
      },
      alternates: [],
    },
  ],
};

const draftB = {
  name: "Banana Bread",
  servings: 4,
  image_url: null,
  source_url: "https://example.com/recipes/banana-bread/",
  instructions: null,
  ingredients: [
    {
      raw_line: "3 bananas",
      quantity: 3,
      unit: "large",
      food_name: "bananas",
      best_match: null,
      alternates: [],
    },
  ],
};

beforeEach(() => {
  localStorage.setItem("token", "test-token");
  global.fetch = jest.fn((url: RequestInfo | URL, opts?: RequestInit) => {
    const u = String(url);
    if (u === "/recipes/bulk-import/discover") {
      return Promise.resolve({
        ok: true,
        json: async () => ({
          urls: [
            "https://example.com/recipes/chocolate-cake/",
            "https://example.com/recipes/banana-bread/",
          ],
        }),
      } as Response);
    }
    if (u === "/recipes/bulk-import/extract") {
      return Promise.resolve({
        ok: true,
        json: async () => ({ drafts: [draftA, draftB] }),
      } as Response);
    }
    if (u === "/recipes" && opts?.method === "POST") {
      const body = JSON.parse(String(opts.body));
      return Promise.resolve({
        ok: true,
        json: async () => ({ id: "new-id", ...body, ingredients: [] }),
      } as Response);
    }
    return Promise.reject(new Error(`Unexpected fetch: ${u}`));
  }) as jest.Mock;
});

afterEach(() => {
  jest.restoreAllMocks();
  localStorage.clear();
});

test("discover shows candidate count, extract loads the review queue, save/skip advance and summarize", async () => {
  render(<BulkRecipeImport onBack={() => {}} userProfile={{ is_admin: true }} />);

  fireEvent.change(screen.getByPlaceholderText("https://example.com/recipes/"), {
    target: { value: "https://example.com/recipes/" },
  });
  fireEvent.click(screen.getByText("Find Recipes"));

  await waitFor(() => {
    expect(screen.getByText("Found 2 candidate links on this page.")).toBeInTheDocument();
  });

  fireEvent.click(screen.getByText("Extract 2 Recipes"));

  await waitFor(() => {
    expect(screen.getByText("Recipe 1 of 2")).toBeInTheDocument();
  });
  expect(screen.getByDisplayValue("Chocolate Cake")).toBeInTheDocument();

  fireEvent.click(screen.getByText("Save & Next"));

  await waitFor(() => {
    expect(screen.getByText("Recipe 2 of 2")).toBeInTheDocument();
  });
  expect(screen.getByDisplayValue("Banana Bread")).toBeInTheDocument();

  fireEvent.click(screen.getByText("Skip & Next"));

  await waitFor(() => {
    expect(screen.getByText("Saved 1 of 2.")).toBeInTheDocument();
  });
});

test("zero candidate links shows a message instead of an empty confirm screen", async () => {
  (global.fetch as jest.Mock).mockImplementationOnce((url: RequestInfo | URL) => {
    if (String(url) === "/recipes/bulk-import/discover") {
      return Promise.resolve({ ok: true, json: async () => ({ urls: [] }) } as Response);
    }
    return Promise.reject(new Error("unexpected"));
  });

  render(<BulkRecipeImport onBack={() => {}} userProfile={{ is_admin: true }} />);

  fireEvent.change(screen.getByPlaceholderText("https://example.com/recipes/"), {
    target: { value: "https://example.com/empty-page/" },
  });
  fireEvent.click(screen.getByText("Find Recipes"));

  await waitFor(() => {
    expect(
      screen.getByText("No recipe links found on that page — for a single recipe, use Import instead.")
    ).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd pakupaku-frontend && CI=true npx --no-install react-scripts test --watchAll=false src/components/BulkRecipeImport.test.tsx`
Expected: FAIL — `Cannot find module './BulkRecipeImport'`

- [ ] **Step 3: Create `BulkRecipeImport.css`**

```css
.bulk-import-root {
  min-height: 100vh;
  padding: 2rem 1rem;
  font-family: "MorningBreeze";
}

.bulk-import-container {
  max-width: 720px;
  margin: 0 auto;
}

.bulk-import-header {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 2rem;
}

.bulk-import-title {
  font-size: 2rem;
  margin: 0 0 0.25rem;
}

.bulk-import-subtitle {
  font-size: 1rem;
  color: #8a6060;
  margin: 0;
}

.bulk-import-card {
  background: #ffffff;
  border-radius: 20px;
  padding: 1.5rem;
  border: 2px solid #badfdb;
  box-shadow: 0 6px 32px rgba(186, 223, 219, 0.22);
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.bulk-import-count {
  font-weight: 600;
  margin: 0;
}

.bulk-import-actions {
  display: flex;
  gap: 0.75rem;
}

.bulk-import-progress {
  font-weight: 600;
  margin: 0 0 0.5rem;
}
```

- [ ] **Step 4: Create `BulkRecipeImport.tsx`**

```tsx
import { useState } from "react";
import "./BulkRecipeImport.css";
// RecipeEditForm.tsx imports RecipeBuilder.css directly, and this file
// always renders RecipeEditForm, so classes like .back-button,
// .recipe-field, .recipe-error, .save-recipe-button, .cancel-edit-button,
// .empty-state, and .recipe-edit-banner (used directly below, not just by
// RecipeEditForm) are guaranteed to be in the bundle via that import chain.
import { apiFetch } from "../apiBase";
import RecipeEditForm, {
  RecipeImportDraft, RecipeSavePayload, formValuesFromDraft,
} from "./RecipeEditForm";

interface BulkRecipeImportProps {
  onBack: () => void;
  userProfile: any;
}

type Step = "input" | "confirm" | "extracting" | "queue" | "summary";

export default function BulkRecipeImport({ onBack, userProfile }: BulkRecipeImportProps) {
  const [step, setStep] = useState<Step>("input");
  const [indexUrl, setIndexUrl] = useState("");
  const [discovering, setDiscovering] = useState(false);
  const [candidateUrls, setCandidateUrls] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [drafts, setDrafts] = useState<RecipeImportDraft[]>([]);
  const [queueIndex, setQueueIndex] = useState(0);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [savedCount, setSavedCount] = useState(0);

  const runDiscover = async () => {
    if (!indexUrl.trim()) {
      setError("Enter a blog index URL.");
      return;
    }
    setError("");
    setDiscovering(true);
    try {
      const token = localStorage.getItem("token");
      const res = await apiFetch("/recipes/bulk-import/discover", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: token ? `Bearer ${token}` : "",
        },
        body: JSON.stringify({ url: indexUrl.trim() }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail || "Could not scan that page.");
      }
      const data = await res.json();
      setCandidateUrls(data.urls ?? []);
      setStep("confirm");
    } catch (err: any) {
      setError(err.message || "Unable to scan that page.");
    } finally {
      setDiscovering(false);
    }
  };

  const runExtract = async () => {
    setError("");
    setStep("extracting");
    try {
      const token = localStorage.getItem("token");
      const res = await apiFetch("/recipes/bulk-import/extract", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: token ? `Bearer ${token}` : "",
        },
        body: JSON.stringify({ urls: candidateUrls }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail || "Extraction failed.");
      }
      const data = await res.json();
      const extracted: RecipeImportDraft[] = data.drafts ?? [];
      setDrafts(extracted);
      setQueueIndex(0);
      setSavedCount(0);
      setStep(extracted.length > 0 ? "queue" : "summary");
    } catch (err: any) {
      setError(err.message || "Extraction failed.");
      setStep("confirm");
    }
  };

  const advanceQueue = () => {
    setSaveError("");
    setQueueIndex(prev => {
      const next = prev + 1;
      if (next >= drafts.length) setStep("summary");
      return next;
    });
  };

  const handleSaveCurrent = async (payload: RecipeSavePayload) => {
    setSaveError("");
    setSaving(true);
    try {
      const token = localStorage.getItem("token");
      const res = await apiFetch("/recipes", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: token ? `Bearer ${token}` : "",
        },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail || "Failed to save recipe.");
      }
      setSavedCount(n => n + 1);
      advanceQueue();
    } catch (err: any) {
      setSaveError(err.message || "Unable to save recipe.");
    } finally {
      setSaving(false);
    }
  };

  const handleSkipCurrent = () => {
    advanceQueue();
  };

  const startOver = () => {
    setStep("input");
    setIndexUrl("");
    setCandidateUrls([]);
    setDrafts([]);
    setQueueIndex(0);
    setSavedCount(0);
    setError("");
    setSaveError("");
  };

  return (
    <div className="bulk-import-root">
      <div className="bulk-import-container">
        <header className="bulk-import-header">
          <button type="button" className="back-button" onClick={onBack}>← Back</button>
          <div>
            <h1 className="bulk-import-title">Bulk import recipes</h1>
            <p className="bulk-import-subtitle">
              Paste a link to a blog's recipe index or category page.
            </p>
          </div>
        </header>

        {step === "input" && (
          <div className="bulk-import-card">
            <label className="recipe-field">
              <span>Blog index URL</span>
              <input
                type="url"
                value={indexUrl}
                onChange={e => setIndexUrl(e.target.value)}
                placeholder="https://example.com/recipes/"
              />
            </label>
            {error && <p className="recipe-error">{error}</p>}
            <button type="button" className="save-recipe-button" onClick={runDiscover} disabled={discovering}>
              {discovering ? "Scanning…" : "Find Recipes"}
            </button>
          </div>
        )}

        {step === "confirm" && (
          <div className="bulk-import-card">
            {candidateUrls.length === 0 ? (
              <p className="empty-state">
                No recipe links found on that page — for a single recipe, use Import instead.
              </p>
            ) : (
              <p className="bulk-import-count">
                Found {candidateUrls.length} candidate link{candidateUrls.length !== 1 ? "s" : ""} on this page.
              </p>
            )}
            {error && <p className="recipe-error">{error}</p>}
            <div className="bulk-import-actions">
              {candidateUrls.length > 0 && (
                <button type="button" className="save-recipe-button" onClick={runExtract}>
                  Extract {candidateUrls.length} Recipe{candidateUrls.length !== 1 ? "s" : ""}
                </button>
              )}
              <button type="button" className="cancel-edit-button" onClick={startOver}>
                {candidateUrls.length === 0 ? "Try another URL" : "Cancel"}
              </button>
            </div>
          </div>
        )}

        {step === "extracting" && (
          <div className="bulk-import-card">
            <p className="bulk-import-count">
              Extracting recipes from {candidateUrls.length} link{candidateUrls.length !== 1 ? "s" : ""}…
            </p>
          </div>
        )}

        {step === "queue" && drafts.length > 0 && queueIndex < drafts.length && (
          <>
            <p className="bulk-import-progress">
              Recipe {queueIndex + 1} of {drafts.length}
            </p>
            <RecipeEditForm
              key={queueIndex}
              initialValues={{ ...formValuesFromDraft(drafts[queueIndex]), isShared: true }}
              userProfile={userProfile}
              onSave={handleSaveCurrent}
              submitLabel="Save & Next"
              savingLabel="Saving…"
              saving={saving}
              submitError={saveError}
              banner={
                <div className="recipe-edit-banner">
                  <span>Imported from {drafts[queueIndex].source_url}</span>
                  <button type="button" className="cancel-edit-button" onClick={handleSkipCurrent}>
                    Skip & Next
                  </button>
                </div>
              }
            />
          </>
        )}

        {step === "summary" && (
          <div className="bulk-import-card">
            <p className="bulk-import-count">
              Saved {savedCount} of {drafts.length}.
            </p>
            <button type="button" className="save-recipe-button" onClick={startOver}>
              Import another blog
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd pakupaku-frontend && CI=true npx --no-install react-scripts test --watchAll=false src/components/BulkRecipeImport.test.tsx`
Expected: PASS (both tests)

- [ ] **Step 6: Run the full frontend build**

Run: `cd pakupaku-frontend && CI=true npm run build`
Expected: `Compiled successfully.`

- [ ] **Step 7: Commit**

```bash
git add pakupaku-frontend/src/components/BulkRecipeImport.tsx pakupaku-frontend/src/components/BulkRecipeImport.css pakupaku-frontend/src/components/BulkRecipeImport.test.tsx
git commit -m "feat: add BulkRecipeImport review-queue screen"
```

---

### Task 6: Wire up the admin-only entry point

**Files:**
- Modify: `pakupaku-frontend/src/components/Dashboard.tsx`
- Modify: `pakupaku-frontend/src/App.tsx`
- Test: `pakupaku-frontend/src/components/Dashboard.test.tsx`

**Interfaces:**
- Consumes: `BulkRecipeImport` (default export) from `./BulkRecipeImport` (Task 5); the existing `AppView` union type and `Dashboard`/`SharedRecipes` wiring pattern already in `App.tsx`.
- Produces: `DashboardProps` gains `onOpenBulkImport: () => void`; `AppView` gains `"bulkImport"`.

- [ ] **Step 1: Write the failing test**

```tsx
// pakupaku-frontend/src/components/Dashboard.test.tsx
import { render, screen } from "@testing-library/react";
import Dashboard from "./Dashboard";

const nutritionData = {
  calories: { consumed: 0, goal: 2000 },
  protein: { consumed: 0, goal: 100 },
  carbs: { consumed: 0, goal: 250 },
  fat: { consumed: 0, goal: 70 },
};

beforeEach(() => {
  localStorage.setItem("token", "test-token");
  global.fetch = jest.fn((url: RequestInfo | URL) => {
    const u = String(url);
    if (u === "/recipes") {
      return Promise.resolve({ ok: true, json: async () => [] } as Response);
    }
    if (u.startsWith("/logs?log_date=")) {
      return Promise.resolve({ ok: true, json: async () => [] } as Response);
    }
    if (u === "/measurements") {
      return Promise.resolve({ ok: true, json: async () => [] } as Response);
    }
    return Promise.reject(new Error(`Unexpected fetch: ${u}`));
  }) as jest.Mock;
});

afterEach(() => {
  jest.restoreAllMocks();
  localStorage.clear();
});

test("Bulk Import button only appears for admins", () => {
  const { rerender } = render(
    <Dashboard
      nutritionData={nutritionData}
      userProfile={{ is_admin: false }}
      onOpenRecipeBuilder={() => {}}
      onOpenSettings={() => {}}
      onOpenSharedRecipes={() => {}}
      onOpenBulkImport={() => {}}
    />
  );
  expect(screen.queryByText("Bulk Import")).not.toBeInTheDocument();

  rerender(
    <Dashboard
      nutritionData={nutritionData}
      userProfile={{ is_admin: true }}
      onOpenRecipeBuilder={() => {}}
      onOpenSettings={() => {}}
      onOpenSharedRecipes={() => {}}
      onOpenBulkImport={() => {}}
    />
  );
  expect(screen.getByText("Bulk Import")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd pakupaku-frontend && CI=true npx --no-install react-scripts test --watchAll=false src/components/Dashboard.test.tsx`
Expected: FAIL — `TypeScript error: Property 'onOpenBulkImport' does not exist on type 'IntrinsicAttributes & DashboardProps'` (or a runtime error if it compiles loosely) since `DashboardProps` doesn't have `onOpenBulkImport` yet.

- [ ] **Step 3: Add `onOpenBulkImport` to `DashboardProps` and the button**

In `pakupaku-frontend/src/components/Dashboard.tsx`, change:

```tsx
interface DashboardProps {
  nutritionData: NutritionData;
  userProfile: any;
  onOpenRecipeBuilder: () => void;
  onOpenSettings: () => void;
  onOpenSharedRecipes: () => void;
}
```

to:

```tsx
interface DashboardProps {
  nutritionData: NutritionData;
  userProfile: any;
  onOpenRecipeBuilder: () => void;
  onOpenSettings: () => void;
  onOpenSharedRecipes: () => void;
  onOpenBulkImport: () => void;
}
```

Change the component signature:

```tsx
export default function Dashboard({ nutritionData, userProfile, onOpenRecipeBuilder, onOpenSettings, onOpenSharedRecipes }: DashboardProps) {
```

to:

```tsx
export default function Dashboard({ nutritionData, userProfile, onOpenRecipeBuilder, onOpenSettings, onOpenSharedRecipes, onOpenBulkImport }: DashboardProps) {
```

Change the header actions block:

```tsx
          <div className="dashboard-header-actions">
            <button type="button" className="secondary-button" onClick={onOpenRecipeBuilder}>
              Create recipe
            </button>
            <button type="button" className="secondary-button" onClick={onOpenSharedRecipes}>Shared recipes</button>
            <button type="button" className="secondary-button" onClick={onOpenSettings}>
              Settings
            </button>
          </div>
```

to:

```tsx
          <div className="dashboard-header-actions">
            <button type="button" className="secondary-button" onClick={onOpenRecipeBuilder}>
              Create recipe
            </button>
            <button type="button" className="secondary-button" onClick={onOpenSharedRecipes}>Shared recipes</button>
            {userProfile?.is_admin && (
              <button type="button" className="secondary-button" onClick={onOpenBulkImport}>Bulk Import</button>
            )}
            <button type="button" className="secondary-button" onClick={onOpenSettings}>
              Settings
            </button>
          </div>
```

- [ ] **Step 4: Wire `App.tsx`**

In `pakupaku-frontend/src/App.tsx`, add the import near the existing `SharedRecipes` import:

```tsx
import BulkRecipeImport from "./components/BulkRecipeImport";
```

Change the `AppView` union type:

```tsx
type AppView = "login" | "verifyEmail" | "onboarding" | "dashboard" | "recipeBuilder" | "settings" | "resetPassword" | "sharedRecipes";
```

to:

```tsx
type AppView = "login" | "verifyEmail" | "onboarding" | "dashboard" | "recipeBuilder" | "settings" | "resetPassword" | "sharedRecipes" | "bulkImport";
```

Change the `Dashboard` render call:

```tsx
  if (view === "dashboard") {
    return <Dashboard
      nutritionData={nutritionData}
      userProfile={userProfile}
      onOpenRecipeBuilder={() => setView("recipeBuilder")}
      onOpenSettings={() => setView("settings")}
      onOpenSharedRecipes={() => setView("sharedRecipes")}
    />;
  }
```

to:

```tsx
  if (view === "dashboard") {
    return <Dashboard
      nutritionData={nutritionData}
      userProfile={userProfile}
      onOpenRecipeBuilder={() => setView("recipeBuilder")}
      onOpenSettings={() => setView("settings")}
      onOpenSharedRecipes={() => setView("sharedRecipes")}
      onOpenBulkImport={() => setView("bulkImport")}
    />;
  }
```

Add a new view branch right after the `sharedRecipes` branch:

```tsx
  if (view === "sharedRecipes") {
    return <SharedRecipes onBack={() => setView("dashboard")} />;
  }
```

becomes:

```tsx
  if (view === "sharedRecipes") {
    return <SharedRecipes onBack={() => setView("dashboard")} />;
  }

  if (view === "bulkImport") {
    return <BulkRecipeImport onBack={() => setView("dashboard")} userProfile={userProfile} />;
  }
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd pakupaku-frontend && CI=true npx --no-install react-scripts test --watchAll=false src/components/Dashboard.test.tsx`
Expected: PASS

- [ ] **Step 6: Run the full frontend test suite and build**

Run: `cd pakupaku-frontend && CI=true npx --no-install react-scripts test --watchAll=false && CI=true npm run build`
Expected: all test suites pass (the pre-existing `App.test.tsx` failure is a known, unrelated stock-CRA-boilerplate issue predating this plan — not a regression to fix here); build compiles successfully.

- [ ] **Step 7: Run the full backend test suite one more time as a final sanity check**

Run: `pytest -v`
Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add pakupaku-frontend/src/components/Dashboard.tsx pakupaku-frontend/src/App.tsx pakupaku-frontend/src/components/Dashboard.test.tsx
git commit -m "feat: wire up admin-only Bulk Import entry point"
```

---

## After merge: hosted deployment

This plan adds no new database columns — `recipe_bulk_import.py` only produces `RecipeImportDraft`s (never persisted directly) and reuses the existing `POST /recipes` save path, so there's no Neon `ALTER TABLE` follow-up like the shared-recipes and gochujang-dedup work needed. Once merged, the new routes and frontend screen work as soon as the hosted backend and frontend redeploy from `main` — no manual database step required.
