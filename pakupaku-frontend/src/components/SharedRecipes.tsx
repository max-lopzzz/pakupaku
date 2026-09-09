import { useEffect, useState } from "react";
import "./SharedRecipes.css";
import { apiFetch } from "../apiBase";

interface SharedIngredient {
  food_name: string;
  brand_name?: string | null;
  amount_g: number;
  calories?: number | null;
}

interface SharedRecipe {
  id: string;
  name: string;
  servings: number;
  image_url?: string | null;
  diet_tags?: string[];
  instructions?: string | null;
  source_url?: string | null;
  ingredients?: SharedIngredient[];
  total_calories?: number;
  total_protein_g?: number;
  total_fat_g?: number;
  total_carbs_g?: number;
  total_fiber_g?: number;
}

const fmt = (v?: number | null) =>
  v == null ? "–" : (Math.round(v * 10) / 10).toString();

type MealCategory = "breakfast" | "lunch" | "dinner" | "snacks";

interface SharedRecipesProps {
  onBack: () => void;
  userProfile?: any;
}

function authHeaders(extra: Record<string, string> = {}) {
  const token = localStorage.getItem("token");
  return { Authorization: token ? `Bearer ${token}` : "", ...extra };
}

export default function SharedRecipes({ onBack, userProfile }: SharedRecipesProps) {
  const isAdmin = !!userProfile?.is_admin;

  const [recipes, setRecipes] = useState<SharedRecipe[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState("");
  const [loggingId, setLoggingId] = useState<string | null>(null);
  const [servings, setServings]   = useState("1");
  const [meal, setMeal]           = useState<MealCategory>("lunch");
  const [copyMessage, setCopyMessage] = useState("");
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [editingId, setEditingId]   = useState<string | null>(null);
  const [editName, setEditName]     = useState("");
  const [editServings, setEditServings] = useState("1");
  const [savingEdit, setSavingEdit] = useState(false);
  const [cleaning, setCleaning]   = useState(false);
  const [cleanupMsg, setCleanupMsg] = useState("");

  const loadShared = async () => {
    const res = await apiFetch("/recipes/shared", { headers: authHeaders() });
    if (!res.ok) throw new Error();
    setRecipes(await res.json());
  };

  useEffect(() => {
    loadShared()
      .catch(() => setError("Unable to load shared recipes."))
      .finally(() => setLoading(false));
  }, []);

  const runCleanup = async () => {
    setError("");
    setCleaning(true);
    setCleanupMsg("Removing duplicates…");
    try {
      const d = await apiFetch("/recipes/shared/dedupe", { method: "POST", headers: authHeaders() });
      if (!d.ok) throw new Error();
      const { deleted } = await d.json();

      setCleanupMsg("Backfilling images…");
      let imagesAdded = 0;
      for (let i = 0; i < 60; i++) {
        const b = await apiFetch("/recipes/shared/backfill-images", { method: "POST", headers: authHeaders() });
        if (!b.ok) throw new Error();
        const { updated, checked, remaining } = await b.json();
        imagesAdded += updated;
        if (checked === 0 || remaining <= 0) break;
      }

      await loadShared();
      setCleanupMsg(
        `Removed ${deleted} duplicate${deleted !== 1 ? "s" : ""}` +
        `, backfilled ${imagesAdded} image${imagesAdded !== 1 ? "s" : ""}.`,
      );
    } catch {
      setError("Cleanup failed. It's safe to run again.");
      setCleanupMsg("");
    } finally {
      setCleaning(false);
    }
  };

  const startLogging = (recipe: SharedRecipe) => {
    setLoggingId(recipe.id);
    setServings("1");
    setMeal("lunch");
  };

  const confirmLog = async (recipe: SharedRecipe) => {
    const n = parseFloat(servings) || 1;
    const scale = (v?: number) => (v != null ? Math.round(v * n * 10) / 10 : undefined);
    try {
      const res = await apiFetch("/logs", {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          recipe_id: recipe.id,
          food_name: recipe.name,
          amount_g:  n * 100, // nominal - recipe totals are per-serving, not per-gram; see plan for reasoning
          calories:  scale(recipe.total_calories),
          protein_g: scale(recipe.total_protein_g),
          fat_g:     scale(recipe.total_fat_g),
          carbs_g:   scale(recipe.total_carbs_g),
          meal,
        }),
      });
      if (!res.ok) throw new Error();
      setLoggingId(null);
    } catch {
      setError("Failed to log that recipe.");
    }
  };

  const deleteRecipe = async (recipe: SharedRecipe) => {
    setError("");
    try {
      const res = await apiFetch(`/recipes/${recipe.id}`, {
        method: "DELETE",
        headers: authHeaders(),
      });
      if (!res.ok) throw new Error();
      setRecipes(rs => rs.filter(r => r.id !== recipe.id));
      setDeletingId(null);
    } catch {
      setError("Failed to delete that recipe.");
    }
  };

  const startEdit = (recipe: SharedRecipe) => {
    setEditingId(recipe.id);
    setEditName(recipe.name);
    setEditServings(String(recipe.servings));
  };

  const saveEdit = async (recipe: SharedRecipe) => {
    setError("");
    setSavingEdit(true);
    try {
      const res = await apiFetch(`/recipes/${recipe.id}`, {
        method: "PATCH",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          name: editName.trim(),
          servings: parseFloat(editServings) || recipe.servings,
        }),
      });
      if (!res.ok) throw new Error();
      const updated = await res.json();
      setRecipes(rs => rs.map(r => (r.id === recipe.id ? { ...r, ...updated } : r)));
      setEditingId(null);
    } catch {
      setError("Failed to save changes.");
    } finally {
      setSavingEdit(false);
    }
  };

  const saveCopy = async (recipe: SharedRecipe) => {
    setCopyMessage("");
    try {
      const res = await apiFetch(`/recipes/${recipe.id}/copy`, {
        method: "POST",
        headers: authHeaders(),
      });
      if (!res.ok) throw new Error();
      setCopyMessage(`Saved a copy of "${recipe.name}" to your recipes.`);
    } catch {
      setError("Failed to save a copy.");
    }
  };

  return (
    <div className="shared-recipes-root">
      <div className="shared-recipes-container">
        <header className="shared-recipes-header">
          <button type="button" className="back-button" onClick={onBack}>← Back</button>
          <h1 className="shared-recipes-title">Shared Recipes</h1>
          {isAdmin && (
            <button
              type="button"
              className="shared-recipes-cleanup-btn"
              onClick={runCleanup}
              disabled={cleaning}
            >
              {cleaning ? "Cleaning up…" : "Clean up duplicates"}
            </button>
          )}
        </header>

        {error && <p className="shared-recipes-error">{error}</p>}
        {copyMessage && <p className="shared-recipes-message">{copyMessage}</p>}
        {cleanupMsg && <p className="shared-recipes-message">{cleanupMsg}</p>}

        {loading ? (
          <div className="empty-state">Loading shared recipes…</div>
        ) : recipes.length === 0 ? (
          <div className="empty-state">No shared recipes yet.</div>
        ) : (
          <div className="shared-recipes-grid">
            {recipes.map(recipe => (
              <div key={recipe.id} className="shared-recipe-card">
                {recipe.image_url && (
                  <img src={recipe.image_url} alt="" className="shared-recipe-image" />
                )}
                <h3>{recipe.name}</h3>
                <span>{recipe.servings} serving{recipe.servings !== 1 ? "s" : ""}</span>
                {recipe.diet_tags && recipe.diet_tags.length > 0 && (
                  <div className="shared-recipe-tags">
                    {recipe.diet_tags.map(tag => (
                      <span key={tag} className="diet-tag-pill">{tag.replace(/_/g, " ")}</span>
                    ))}
                  </div>
                )}
                {recipe.ingredients && recipe.ingredients.length > 0 && (
                  <ul className="shared-recipe-ingredients">
                    {recipe.ingredients.map((ing, i) => (
                      <li key={i}>
                        {ing.food_name}
                        {ing.brand_name ? ` (${ing.brand_name})` : ""}
                        {" — "}
                        {Math.round(ing.amount_g)} g
                      </li>
                    ))}
                  </ul>
                )}

                <div className="shared-recipe-nutrition">
                  <span className="shared-recipe-nutrition-label">Per serving</span>
                  <span>{fmt(recipe.total_calories)} kcal</span>
                  <span>{fmt(recipe.total_protein_g)} g protein</span>
                  <span>{fmt(recipe.total_fat_g)} g fat</span>
                  <span>{fmt(recipe.total_carbs_g)} g carbs</span>
                  {recipe.total_fiber_g != null && (
                    <span>{fmt(recipe.total_fiber_g)} g fiber</span>
                  )}
                </div>
                {recipe.source_url && (
                  <a href={recipe.source_url} target="_blank" rel="noreferrer" className="saved-recipe-source-link">
                    View original
                  </a>
                )}
                <div className="shared-recipe-actions">
                  <button type="button" onClick={() => startLogging(recipe)}>Log now</button>
                  <button type="button" onClick={() => saveCopy(recipe)}>Save a copy</button>
                  {isAdmin && (
                    <>
                      <button type="button" onClick={() => startEdit(recipe)}>Edit</button>
                      <button type="button" onClick={() => setDeletingId(recipe.id)}>Delete</button>
                    </>
                  )}
                </div>

                {isAdmin && editingId === recipe.id && (
                  <div className="shared-recipe-admin-form">
                    <label>
                      <span>Name</span>
                      <input
                        type="text"
                        value={editName}
                        onChange={e => setEditName(e.target.value)}
                      />
                    </label>
                    <label>
                      <span>Servings</span>
                      <input
                        type="number"
                        min="0.25"
                        step="0.25"
                        value={editServings}
                        onChange={e => setEditServings(e.target.value)}
                      />
                    </label>
                    <div className="shared-recipe-admin-form-actions">
                      <button type="button" disabled={savingEdit} onClick={() => saveEdit(recipe)}>
                        {savingEdit ? "Saving…" : "Save changes"}
                      </button>
                      <button type="button" onClick={() => setEditingId(null)}>Cancel</button>
                    </div>
                  </div>
                )}

                {isAdmin && deletingId === recipe.id && (
                  <div className="shared-recipe-admin-form">
                    <p>Delete "{recipe.name}" for everyone?</p>
                    <div className="shared-recipe-admin-form-actions">
                      <button type="button" onClick={() => deleteRecipe(recipe)}>Confirm delete</button>
                      <button type="button" onClick={() => setDeletingId(null)}>Cancel</button>
                    </div>
                  </div>
                )}
                {loggingId === recipe.id && (
                  <div className="log-recipe-form">
                    <label>
                      <span>Servings</span>
                      <input type="number" min="0.25" step="0.25" value={servings}
                        onChange={e => setServings(e.target.value)} />
                    </label>
                    <label>
                      <span>Meal</span>
                      <select value={meal} onChange={e => setMeal(e.target.value as MealCategory)}>
                        <option value="breakfast">Breakfast</option>
                        <option value="lunch">Lunch</option>
                        <option value="dinner">Dinner</option>
                        <option value="snacks">Snacks</option>
                      </select>
                    </label>
                    <button type="button" onClick={() => confirmLog(recipe)}>Confirm</button>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
