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

/** Natural units are food-specific portions from the food database that aren't in our standard list. */
function naturalUnits(portionsMap: Record<string, number>): string[] {
  return Object.keys(portionsMap).filter(u => !STANDARD_UNIT_SET.has(u));
}

// portionsMap overrides the generic table with food-specific gram weights from the food database
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

// ─── Nutrient shape ───────────────────────────────────────

interface NutrientData {
  calories_per_100g: number | null;
  protein_per_100g:  number | null;
  fat_per_100g:      number | null;
  carbs_per_100g:    number | null;
  fiber_per_100g:    number | null;
}

// ─── Types ────────────────────────────────────────────────

interface FoodSuggestion extends NutrientData {
  food_id:     string;
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

  // resolved food
  food_id:   string | null;
  food_name: string;
  brand_name: string;

  // food-specific unit → grams from the food database (overrides generic UNIT_TO_G)
  portionsMap: Record<string, number>;

  // amount
  amount: string;
  unit:   string;
}

function blankRow(): IngredientRow {
  return {
    mode: "search",
    query: "", suggestions: [], showDropdown: false,
    food_id: null, food_name: "", brand_name: "",
    calories_per_100g: null, protein_per_100g: null,
    fat_per_100g: null, carbs_per_100g: null, fiber_per_100g: null,
    portionsMap: {},
    amount: "", unit: "g",
  };
}

interface SavedIngredient {
  id:          string;
  food_id?:    string;
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
  food_id:     string;
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
    food_id: match ? match.food_id : null,
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
    const isCustom = ing.food_id == null;
    const per100 = (v?: number) =>
      v != null && ing.amount_g > 0 ? (v / ing.amount_g) * 100 : null;
    return {
      mode:              isCustom ? "custom" : "search",
      query:             ing.food_name,
      suggestions:       [],
      showDropdown:      false,
      food_id:           ing.food_id ?? null,
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
    food_id?: string;
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
          food_id:    r.food_id ?? undefined,
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
      {submitMessage && !validationError && !submitError && <p className="recipe-success">{submitMessage}</p>}
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

  // Close the dropdown on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        onUpdate({ showDropdown: false });
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [onUpdate]);

  const runSearch = (query: string) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (query.trim().length < 2) {
      onUpdate({ suggestions: [], showDropdown: false });
      return;
    }
    debounceRef.current = setTimeout(async () => {
      try {
        const token = localStorage.getItem("token");
        const url = `/foods/search?query=${encodeURIComponent(query.trim())}&page_size=50`;
        const res = await apiFetch(url, { headers: { Authorization: token ? `Bearer ${token}` : "" } });
        if (!res.ok) return;
        const data = await res.json();

        const suggestions: FoodSuggestion[] = (data.foods ?? []).map((f: any) => ({
          food_id:     f.food_id,
          description: f.description,
          brand:       null,
          calories_per_100g: f.calories_per_100g ?? null,
          protein_per_100g:  f.protein_per_100g  ?? null,
          fat_per_100g:      f.fat_per_100g      ?? null,
          carbs_per_100g:    f.carbs_per_100g    ?? null,
          fiber_per_100g:    f.fiber_per_100g    ?? null,
        }));
        onUpdate({ suggestions, showDropdown: suggestions.length > 0 });
      } catch { /* silently ignore */ }
    }, 350);
  };

  const handleQueryChange = (value: string) => {
    onUpdate({ query: value, food_name: value, food_id: null });
    runSearch(value);
  };

  const handleBrandChange = (value: string) => {
    onUpdate({ brand_name: value });
  };

  const selectFood = async (food: FoodSuggestion) => {
    // Immediately fill what we already know from the search result
    onUpdate({
      query:             food.description,
      food_name:         food.description,
      brand_name:        food.brand ?? "",
      food_id:           food.food_id,
      calories_per_100g: food.calories_per_100g,
      protein_per_100g:  food.protein_per_100g,
      fat_per_100g:      food.fat_per_100g,
      carbs_per_100g:    food.carbs_per_100g,
      fiber_per_100g:    food.fiber_per_100g,
      suggestions:       [],
      showDropdown:      false,
    });

    // Fetch food-specific portion gram weights from the offline index.
    const token = localStorage.getItem("token");
    const headers = { Authorization: token ? `Bearer ${token}` : "" };

    const fetchPortions = async (foodId: string): Promise<Record<string, number> | null> => {
      try {
        const res = await apiFetch(`/foods/${encodeURIComponent(foodId)}`, { headers });
        if (!res.ok) return null;
        const detail = await res.json();
        const map: Record<string, number> = {};
        for (const p of detail.portions ?? []) {
          if (p.unit && p.grams) map[p.unit] = p.grams;
        }
        return Object.keys(map).length > 0 ? map : null;
      } catch {
        return null;
      }
    };

    const portionsMap = await fetchPortions(food.food_id);

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
                    key={food.food_id}
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
            ? { mode: "search", food_name: "", query: "", food_id: null,
                calories_per_100g: null, protein_per_100g: null,
                fat_per_100g: null, carbs_per_100g: null, fiber_per_100g: null }
            : { mode: "custom", suggestions: [], showDropdown: false, food_id: null,
                portionsMap: {} }
          )}
        >
          {isCustom ? "↩ search foods" : "enter manually"}
        </button>
      </div>

      {/* Brand — plain text; a user can still type a brand for a custom food */}
      <div className="ingredient-brand-wrap">
        <input
          type="text"
          className="ingredient-input"
          placeholder="Brand (optional)"
          value={row.brand_name}
          onChange={e => handleBrandChange(e.target.value)}
          autoComplete="off"
        />
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
