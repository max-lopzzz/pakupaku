import { useState, useEffect, useRef } from "react";
import "./RecipeBuilder.css";

// ─── Unit conversion ──────────────────────────────────────

const UNIT_TO_G: Record<string, number> = {
  g:    1,
  ml:   1,
  oz:   28.3495,
  cup:  240,
  tbsp: 15,
  tsp:  5,
};
const STANDARD_UNITS = ["g", "ml", "oz", "cup", "tbsp", "tsp"];
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

interface IngredientRow extends NutrientData {
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

interface RecipeResponse {
  id:              string;
  name:            string;
  description?:    string;
  servings:        number;
  total_calories?: number;
  total_protein_g?: number;
  total_fat_g?:    number;
  total_carbs_g?:  number;
  total_fiber_g?:  number;
  ingredients: SavedIngredient[];
}

interface RecipeBuilderProps {
  onBack: () => void;
}

// ─── Main component ───────────────────────────────────────

export default function RecipeBuilder({ onBack }: RecipeBuilderProps) {
  const [name, setName]             = useState("");
  const [description, setDescription] = useState("");
  const [servings, setServings]     = useState("1");
  const [ingredients, setIngredients] = useState<IngredientRow[]>([blankRow()]);
  const [recipes, setRecipes]       = useState<RecipeResponse[]>([]);
  const [loading, setLoading]       = useState(false);
  const [message, setMessage]       = useState("");
  const [error, setError]           = useState("");
  const [editingId, setEditingId]   = useState<string | null>(null);

  const fetchRecipes = async () => {
    try {
      const token = localStorage.getItem("token");
      const res = await fetch("/recipes", {
        headers: { Authorization: token ? `Bearer ${token}` : "" },
      });
      if (!res.ok) throw new Error("Could not load recipes.");
      setRecipes(await res.json());
    } catch {
      setError("Unable to load saved recipes.");
    }
  };

  useEffect(() => { fetchRecipes(); }, []);

  const updateRow = (index: number, patch: Partial<IngredientRow>) => {
    setIngredients(prev =>
      prev.map((row, i) => i === index ? { ...row, ...patch } : row)
    );
  };

  const addIngredient = () =>
    setIngredients(prev => [...prev, blankRow()]);

  const removeIngredient = (index: number) =>
    setIngredients(prev => prev.filter((_, i) => i !== index));

  const startEdit = (recipe: RecipeResponse) => {
    setEditingId(recipe.id);
    setName(recipe.name);
    setDescription(recipe.description ?? "");
    setServings(String(recipe.servings));
    setError("");
    setMessage("");
    // Reconstruct ingredient rows from saved data — nutrients are already
    // per-amount_g in the DB, so we store them back as per-100g by reversing.
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
    setIngredients(rows.length > 0 ? rows : [blankRow()]);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const cancelEdit = () => {
    setEditingId(null);
    setName(""); setDescription(""); setServings("1");
    setIngredients([blankRow()]);
    setError(""); setMessage("");
  };

  const handleSave = async () => {
    setError("");
    setMessage("");

    if (!name.trim()) {
      setError("Recipe name is required.");
      return;
    }

    const valid = ingredients.filter(r => r.food_name.trim() && parseFloat(r.amount) > 0);
    if (valid.length === 0) {
      setError("Add at least one ingredient with a name and amount.");
      return;
    }

    const payload = {
      name:        name.trim(),
      description: description.trim() || undefined,
      servings:    parseFloat(servings) || 1,
      ingredients: valid.map(r => {
        const amount_g = Math.max(toGrams(r.amount, r.unit, r.portionsMap), 0.01);
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

    setLoading(true);
    try {
      const token = localStorage.getItem("token");
      const isEdit = editingId !== null;
      const url    = isEdit ? `/recipes/${editingId}` : "/recipes";
      const method = isEdit ? "PATCH" : "POST";

      const res = await fetch(url, {
        method,
        headers: {
          "Content-Type": "application/json",
          Authorization: token ? `Bearer ${token}` : "",
        },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => null);
        console.error("Recipe save failed:", JSON.stringify(payload), body);
        throw new Error(Array.isArray(body?.detail)
          ? body.detail.map((e: any) => `${e.loc?.slice(-1)[0]}: ${e.msg}`).join("; ")
          : body?.detail || "Failed to save recipe.");
      }

      const saved = await res.json();
      setRecipes(prev =>
        isEdit
          ? prev.map(r => r.id === saved.id ? saved : r)
          : [saved, ...prev]
      );
      setMessage(isEdit ? "Recipe updated!" : "Recipe saved!");
      setEditingId(null);
      setName(""); setDescription(""); setServings("1");
      setIngredients([blankRow()]);
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
            {editingId && (
              <div className="recipe-edit-banner">
                <span>Editing recipe</span>
                <button type="button" className="cancel-edit-button" onClick={cancelEdit}>
                  Cancel
                </button>
              </div>
            )}
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

            {error   && <p className="recipe-error">{error}</p>}
            {message && <p className="recipe-success">{message}</p>}
            <button type="button" className="save-recipe-button"
              onClick={handleSave} disabled={loading}>
              {loading ? "Saving..." : editingId ? "Update recipe" : "Save recipe"}
            </button>
          </div>
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
                  <div className="saved-recipe-stats">
                    <span>{recipe.total_calories != null ? Math.round(recipe.total_calories) : "—"} cal</span>
                    <span>{recipe.total_protein_g != null ? Math.round(recipe.total_protein_g) : "—"}g P</span>
                    <span>{recipe.total_carbs_g != null ? Math.round(recipe.total_carbs_g) : "—"}g C</span>
                    <span>{recipe.total_fat_g != null ? Math.round(recipe.total_fat_g) : "—"}g F</span>
                  </div>
                  <div className="recipe-card-actions">
                    <button
                      type="button"
                      className="edit-recipe-button"
                      onClick={() => startEdit(recipe)}
                      disabled={editingId === recipe.id}
                    >
                      {editingId === recipe.id ? "Editing…" : "Edit"}
                    </button>
                    <button
                      type="button"
                      className="delete-recipe-button"
                      disabled={editingId === recipe.id}
                      onClick={async () => {
                        if (!window.confirm(`Delete "${recipe.name}"?`)) return;
                        const token = localStorage.getItem("token");
                        const res = await fetch(`/recipes/${recipe.id}`, {
                          method: "DELETE",
                          headers: { Authorization: token ? `Bearer ${token}` : "" },
                        });
                        if (res.ok) {
                          setRecipes(prev => prev.filter(r => r.id !== recipe.id));
                          if (editingId === recipe.id) cancelEdit();
                        }
                      }}
                    >
                      Delete
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
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
        const res = await fetch(url, { headers: { Authorization: token ? `Bearer ${token}` : "" } });
        if (!res.ok) return;
        const data = await res.json();

        // Prefer generic foods; fall back to branded if no generic results exist
        const all     = data.foods ?? [];
        const generic = all.filter((f: any) => f.dataType !== "Branded");
        const branded = all.filter((f: any) => f.dataType === "Branded");
        const pool    = hasBrand ? branded : (generic.length > 0 ? generic : branded);

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
        const res = await fetch(
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
        const res = await fetch(`/foods/${fdc_id}`, { headers });
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
        const res = await fetch(
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
