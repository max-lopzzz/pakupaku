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
