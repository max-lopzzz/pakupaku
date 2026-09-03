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

// The /recipes/bulk-import/extract endpoint returns every draft in one
// blocking response, so we send the candidate URLs a chunk at a time and
// advance a progress bar as each chunk comes back. A blog archive can
// now yield hundreds of links (pagination is followed during discovery),
// and that request would otherwise look frozen for minutes.
const EXTRACT_CHUNK_SIZE = 15;

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
  const [processedCount, setProcessedCount] = useState(0);
  const [foundCount, setFoundCount] = useState(0);
  const [extractNotice, setExtractNotice] = useState("");

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
    setExtractNotice("");
    setProcessedCount(0);
    setFoundCount(0);
    setStep("extracting");

    const token = localStorage.getItem("token");
    const chunks: string[][] = [];
    for (let i = 0; i < candidateUrls.length; i += EXTRACT_CHUNK_SIZE) {
      chunks.push(candidateUrls.slice(i, i + EXTRACT_CHUNK_SIZE));
    }

    const collected: RecipeImportDraft[] = [];
    let processed = 0;

    for (const chunk of chunks) {
      let res: Response | null = null;
      try {
        res = await apiFetch("/recipes/bulk-import/extract", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: token ? `Bearer ${token}` : "",
          },
          body: JSON.stringify({ urls: chunk }),
        });
      } catch {
        res = null;
      }

      if (!res || !res.ok) {
        if (collected.length > 0) {
          // Keep the chunks that did come back — the admin can review
          // those now rather than losing the whole run to one bad batch.
          setDrafts(collected);
          setQueueIndex(0);
          setSavedCount(0);
          setExtractNotice(
            `Extraction stopped early — processed ${processed} of ${candidateUrls.length} ` +
            `link${candidateUrls.length !== 1 ? "s" : ""}. ${collected.length} ` +
            `recipe${collected.length !== 1 ? "s" : ""} ready to review.`,
          );
        } else {
          const body = res ? await res.json().catch(() => null) : null;
          setError(body?.detail || "Extraction failed.");
          setStep("confirm");
        }
        return;
      }

      const data = await res.json();
      const chunkDrafts: RecipeImportDraft[] = data.drafts ?? [];
      collected.push(...chunkDrafts);
      processed += chunk.length;
      setProcessedCount(processed);
      setFoundCount(collected.length);
    }

    setDrafts(collected);
    setQueueIndex(0);
    setSavedCount(0);
    setStep(collected.length > 0 ? "queue" : "summary");
  };

  const extractPct = candidateUrls.length
    ? Math.round((processedCount / candidateUrls.length) * 100)
    : 0;

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
    setProcessedCount(0);
    setFoundCount(0);
    setExtractNotice("");
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
            {extractNotice ? (
              <>
                <p className="recipe-error">{extractNotice}</p>
                <div className="bulk-import-actions">
                  <button
                    type="button"
                    className="save-recipe-button"
                    onClick={() => setStep(drafts.length > 0 ? "queue" : "summary")}
                  >
                    Review {drafts.length} recipe{drafts.length !== 1 ? "s" : ""}
                  </button>
                  <button type="button" className="cancel-edit-button" onClick={startOver}>
                    Start over
                  </button>
                </div>
              </>
            ) : (
              <>
                <p className="bulk-import-count">
                  Processing {processedCount} of {candidateUrls.length} link
                  {candidateUrls.length !== 1 ? "s" : ""}…
                </p>
                <div
                  className="bulk-import-progress-bar"
                  role="progressbar"
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={extractPct}
                >
                  <div
                    className="bulk-import-progress-fill"
                    style={{ width: `${extractPct}%` }}
                  />
                </div>
                <p className="bulk-import-subtle">
                  {foundCount} recipe{foundCount !== 1 ? "s" : ""} found so far
                </p>
              </>
            )}
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
