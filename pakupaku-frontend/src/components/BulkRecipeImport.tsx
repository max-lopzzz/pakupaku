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
              {drafts.length === 0
                ? "Found 0 recipes in that batch."
                : `Saved ${savedCount} of ${drafts.length}.`}
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
