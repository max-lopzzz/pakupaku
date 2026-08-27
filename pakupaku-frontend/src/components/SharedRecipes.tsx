import { useEffect, useState } from "react";
import "./SharedRecipes.css";
import { apiFetch } from "../apiBase";

interface SharedRecipe {
  id: string;
  name: string;
  servings: number;
  image_url?: string | null;
  diet_tags?: string[];
  instructions?: string | null;
  source_url?: string | null;
  total_calories?: number;
  total_protein_g?: number;
  total_fat_g?: number;
  total_carbs_g?: number;
}

type MealCategory = "breakfast" | "lunch" | "dinner" | "snacks";

interface SharedRecipesProps {
  onBack: () => void;
}

function authHeaders(extra: Record<string, string> = {}) {
  const token = localStorage.getItem("token");
  return { Authorization: token ? `Bearer ${token}` : "", ...extra };
}

export default function SharedRecipes({ onBack }: SharedRecipesProps) {
  const [recipes, setRecipes] = useState<SharedRecipe[]>([]);
  const [error, setError]     = useState("");
  const [loggingId, setLoggingId] = useState<string | null>(null);
  const [servings, setServings]   = useState("1");
  const [meal, setMeal]           = useState<MealCategory>("lunch");
  const [copyMessage, setCopyMessage] = useState("");

  useEffect(() => {
    const fetchShared = async () => {
      try {
        const res = await apiFetch("/recipes/shared", { headers: authHeaders() });
        if (!res.ok) throw new Error();
        setRecipes(await res.json());
      } catch {
        setError("Unable to load shared recipes.");
      }
    };
    fetchShared();
  }, []);

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
        </header>

        {error && <p className="shared-recipes-error">{error}</p>}
        {copyMessage && <p className="shared-recipes-message">{copyMessage}</p>}

        {recipes.length === 0 ? (
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
                <div className="shared-recipe-actions">
                  <button type="button" onClick={() => startLogging(recipe)}>Log now</button>
                  <button type="button" onClick={() => saveCopy(recipe)}>Save a copy</button>
                </div>
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
