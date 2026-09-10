import { useEffect, useState } from "react";
import "./MealPlanner.css";
import { apiFetch } from "../apiBase";

const DIET_TAGS = [
  "vegan", "vegetarian", "pescatarian", "flexitarian",
  "gluten_free", "dairy_free", "nut_free", "soy_free", "egg_free", "shellfish_free",
  "keto", "low_carb", "paleo", "whole30", "low_fodmap",
  "diabetic_friendly", "low_sodium", "low_fat", "high_protein",
  "halal", "kosher", "mediterranean", "dash",
];

interface RecipeMini {
  id: string; name: string; image_url: string | null;
}
interface Entry {
  id: string; slot: string; servings: number; unfilled: boolean;
  recipe: RecipeMini | null;
  calories: number | null; protein_g: number | null; fat_g: number | null; carbs_g: number | null;
}
interface Day {
  day_index: number; logged_at: string | null;
  structurally_unfilled_slots: string[];
  totals: Record<string, number>;
  entries: Entry[];
}
interface Plan {
  id: string; days: number; meals_per_day: number;
  targets: { kcal: number | null; protein_g: number | null; fat_g: number | null; carbs_g: number | null };
  plan_days: Day[];
}

interface Props { onBack: () => void; userProfile: any; }

function authHeaders(extra: Record<string, string> = {}) {
  const token = localStorage.getItem("token");
  return { Authorization: token ? `Bearer ${token}` : "", ...extra };
}

const dayLabel = (i: number) => (i === 0 ? "Today" : i === 1 ? "Tomorrow" : `Day ${i + 1}`);
const num = (v: number | null | undefined) => (v == null ? "–" : Math.round(v).toString());
const bar = (actual: number | undefined, target: number | null) => {
  if (!target || !actual) return 0;
  return Math.min(100, Math.round((actual / target) * 100));
};

export default function MealPlanner({ onBack, userProfile }: Props) {
  const safeMode = !!userProfile?.safe_mode;
  const [plan, setPlan] = useState<Plan | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState("");

  const [days, setDays] = useState(3);
  const [mealsPerDay, setMealsPerDay] = useState(3);
  const [tags, setTags] = useState<string[]>(userProfile?.diet_tags ?? []);
  const [showForm, setShowForm] = useState(false);
  const [busyEntry, setBusyEntry] = useState<string | null>(null);

  useEffect(() => {
    apiFetch("/meal-plan", { headers: authHeaders() })
      .then(r => (r.ok ? r.json() : null))
      .then((p: Plan | null) => { setPlan(p); setShowForm(p == null); })
      .catch(() => setError("Couldn't load your meal plan."))
      .finally(() => setLoading(false));
  }, []);

  const toggleTag = (t: string) =>
    setTags(ts => (ts.includes(t) ? ts.filter(x => x !== t) : [...ts, t]));

  const generate = async () => {
    setError("");
    setGenerating(true);
    try {
      const res = await apiFetch("/meal-plan/generate", {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ days, meals_per_day: mealsPerDay, diet_tags: tags }),
      });
      const body = await res.json();
      if (!res.ok) { setError(body?.detail || "Couldn't generate a plan."); return; }
      setPlan(body);
      setShowForm(false);
    } catch {
      setError("Couldn't generate a plan.");
    } finally {
      setGenerating(false);
    }
  };

  const swap = async (entryId: string) => {
    setBusyEntry(entryId);
    setError("");
    try {
      const res = await apiFetch(`/meal-plan/entries/${entryId}/swap`, {
        method: "POST", headers: authHeaders(),
      });
      const body = await res.json();
      if (!res.ok) { setError(body?.detail || "Couldn't swap that meal."); return; }
      setPlan(p => {
        if (!p) return p;
        return {
          ...p,
          plan_days: p.plan_days.map(d => ({
            ...d,
            totals: d.entries.some(e => e.id === entryId) ? body.day_totals : d.totals,
            entries: d.entries.map(e => (e.id === entryId ? body.entry : e)),
          })),
        };
      });
    } catch {
      setError("Couldn't swap that meal.");
    } finally {
      setBusyEntry(null);
    }
  };

  const logDay = async (dayIndex: number, force = false): Promise<void> => {
    setError("");
    try {
      const res = await apiFetch(`/meal-plan/days/${dayIndex}/log`, {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ force }),
      });
      const body = await res.json();
      if (res.status === 409 && !force) {
        if (window.confirm("This day was already logged. Log it again?")) return logDay(dayIndex, true);
        return;
      }
      if (!res.ok) { setError(body?.detail || "Couldn't log that day."); return; }
      setPlan(p => p && {
        ...p,
        plan_days: p.plan_days.map(d =>
          d.day_index === dayIndex ? { ...d, logged_at: body.logged_at } : d),
      });
    } catch {
      setError("Couldn't log that day.");
    }
  };

  return (
    <div className="meal-planner-root">
      <div className="meal-planner-container">
        <header className="meal-planner-header">
          <button type="button" className="back-button" onClick={onBack}>← Back</button>
          <h1 className="meal-planner-title">Meal Planner</h1>
          {plan && !showForm && (
            <button type="button" className="meal-planner-regen" onClick={() => setShowForm(true)}>
              Regenerate
            </button>
          )}
        </header>

        {error && <p className="meal-planner-error">{error}</p>}
        {loading && <p className="empty-state">Loading…</p>}

        {!loading && showForm && (
          <div className="meal-planner-form">
            <label className="meal-planner-field">
              <span>Days</span>
              <input type="number" min={1} max={7} value={days}
                onChange={e => setDays(Math.min(7, Math.max(1, Number(e.target.value) || 1)))} />
            </label>
            <label className="meal-planner-field">
              <span>Meals per day</span>
              <select value={mealsPerDay} onChange={e => setMealsPerDay(Number(e.target.value))}>
                <option value={2}>2</option><option value={3}>3</option><option value={4}>4</option>
              </select>
            </label>
            <fieldset className="meal-planner-tags">
              <legend>Dietary filters</legend>
              {DIET_TAGS.map(t => (
                <label key={t}>
                  <input type="checkbox" checked={tags.includes(t)} onChange={() => toggleTag(t)} />
                  {t.replace(/_/g, " ")}
                </label>
              ))}
            </fieldset>
            <button type="button" className="meal-planner-generate" disabled={generating} onClick={generate}>
              {generating ? "Building your plan…" : "Generate plan"}
            </button>
          </div>
        )}

        {!loading && !showForm && plan && (
          <div className="meal-planner-days">
            {plan.plan_days.map(day => (
              <section key={day.day_index} className="meal-planner-day">
                <h2>{dayLabel(day.day_index)}</h2>
                <div className="meal-planner-entries">
                  {day.entries.map(e => (
                    <div key={e.id} className="meal-planner-entry" data-slot={e.slot}>
                      {e.unfilled ? (
                        <div className="meal-planner-entry-empty">
                          No {e.slot} recipe available
                          {day.structurally_unfilled_slots.includes(e.slot)
                            ? ` — add one with meal type "${e.slot}"` : ""}
                        </div>
                      ) : (
                        <>
                          {e.recipe?.image_url && (
                            <img src={e.recipe.image_url} alt="" className="meal-planner-entry-img" />
                          )}
                          <div className="meal-planner-entry-body">
                            <span className="meal-planner-slot">{e.slot}</span>
                            <span className="meal-planner-recipe-name">{e.recipe?.name}</span>
                            <span className="meal-planner-servings">
                              {e.servings} serving{e.servings === 1 ? "" : "s"}
                            </span>
                            {!safeMode && (
                              <span className="meal-planner-entry-macros">
                                {num(e.calories)} kcal · {num(e.protein_g)}p · {num(e.fat_g)}f · {num(e.carbs_g)}c
                              </span>
                            )}
                            <button type="button" className="meal-planner-swap"
                              disabled={busyEntry === e.id} onClick={() => swap(e.id)}>
                              {busyEntry === e.id ? "Swapping…" : "Swap"}
                            </button>
                          </div>
                        </>
                      )}
                    </div>
                  ))}
                </div>
                <div className="meal-planner-totals">
                  {(["calories", "protein_g", "fat_g", "carbs_g"] as const).map(k => {
                    const tgt = k === "calories" ? plan.targets.kcal : (plan.targets as any)[k];
                    return (
                      <div key={k} className="meal-planner-total">
                        <span className="meal-planner-total-label">
                          {k === "calories" ? "kcal" : k.replace("_g", "")}
                        </span>
                        <div className="meal-planner-total-bar">
                          <div className="meal-planner-total-fill"
                               style={{ width: `${bar(day.totals[k], tgt)}%` }} />
                        </div>
                        {!safeMode && (
                          <span className="meal-planner-total-num">
                            {num(day.totals[k])}{tgt ? ` / ${num(tgt)}` : ""}
                          </span>
                        )}
                      </div>
                    );
                  })}
                </div>
                <button type="button" className="meal-planner-logday"
                  disabled={!!day.logged_at} onClick={() => logDay(day.day_index)}>
                  {day.logged_at ? "Logged ✓" : "Log this day"}
                </button>
              </section>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
