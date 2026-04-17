import { useState, useCallback } from "react";
import "./MealPlanner.css";

// ─── Types ────────────────────────────────────────────────

interface MealItem {
  id:               number;
  title:            string;
  image:            string;
  ready_in_minutes: number | null;
  servings:         number | null;
  source_url:       string;
  calories:         number;
  protein_g:        number;
  fat_g:            number;
  carbs_g:          number;
  fiber_g:          number;
  ingredients:      { name: string; amount: number; unit: string }[];
}

interface DayPlan {
  day:            string;
  meals:          { breakfast: MealItem | null; lunch: MealItem | null; dinner: MealItem | null; snack: MealItem | null };
  total_calories: number;
}

interface ShoppingItem {
  name:   string;
  amount: number;
  unit:   string;
}

interface WeeklyPlan {
  week:          DayPlan[];
  shopping_list: ShoppingItem[];
}

interface MealPlannerProps {
  userProfile: any;
  onBack:      () => void;
  onUpgrade:   () => void;
}

// ─── Constants ────────────────────────────────────────────

const DAYS_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

const MEAL_LABELS: Record<string, { emoji: string; label: string }> = {
  breakfast: { emoji: "🌅", label: "Breakfast" },
  lunch:     { emoji: "☀️",  label: "Lunch"     },
  dinner:    { emoji: "🌙", label: "Dinner"    },
  snack:     { emoji: "🍎", label: "Snack"     },
};

const DIET_OPTIONS = [
  { value: "",             label: "No preference" },
  { value: "vegetarian",  label: "Vegetarian"     },
  { value: "vegan",       label: "Vegan"          },
  { value: "gluten free", label: "Gluten-free"    },
  { value: "ketogenic",   label: "Keto"           },
  { value: "paleo",       label: "Paleo"          },
];

// ─── Paywall ──────────────────────────────────────────────

function Paywall({ onBack, onUpgrade }: { onBack: () => void; onUpgrade: () => void }) {
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState("");

  const handleUpgrade = async () => {
    setLoading(true);
    setError("");
    try {
      const token = localStorage.getItem("token");
      const res = await fetch("/users/me/upgrade", {
        method:  "POST",
        headers: { Authorization: `Bearer ${token ?? ""}` },
      });
      if (!res.ok) throw new Error();
      onUpgrade(); // refresh user profile in parent
    } catch {
      setError("Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mp-root">
      <div className="mp-container">
        <button className="mp-back-btn" onClick={onBack}>← Back</button>
        <div className="mp-paywall">
          <div className="mp-paywall-icon">🗓</div>
          <h2 className="mp-paywall-title">Weekly Meal Planner</h2>
          <p className="mp-paywall-desc">
            Get a personalised 7-day meal plan built around your calorie goal
            and macro targets — with a complete shopping list included.
          </p>
          <ul className="mp-paywall-features">
            <li>🌅 Breakfast, lunch, dinner &amp; snack every day</li>
            <li>🎯 Recipes matched to your calorie &amp; macro goals</li>
            <li>🥗 Diet filters (vegetarian, vegan, keto and more)</li>
            <li>🛒 Auto-generated weekly shopping list</li>
            <li>🔄 Regenerate anytime for fresh ideas</li>
          </ul>
          {error && <p className="mp-error">{error}</p>}
          {/* TODO: replace this button with real payment flow before going live */}
          <button
            className="mp-upgrade-btn"
            onClick={handleUpgrade}
            disabled={loading}
          >
            {loading ? "Unlocking…" : "Unlock Premium"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Meal card ────────────────────────────────────────────

function MealCard({ type, meal }: { type: string; meal: MealItem | null }) {
  const meta = MEAL_LABELS[type];

  if (!meal) {
    return (
      <div className="mp-meal-card mp-meal-card--empty">
        <span className="mp-meal-type">{meta.emoji} {meta.label}</span>
        <p className="mp-meal-empty">No suggestion available</p>
      </div>
    );
  }

  return (
    <div className="mp-meal-card">
      <span className="mp-meal-type">{meta.emoji} {meta.label}</span>
      {meal.image && (
        <img src={meal.image} alt={meal.title} className="mp-meal-img" loading="lazy" />
      )}
      <div className="mp-meal-body">
        <h3 className="mp-meal-title">
          {meal.source_url
            ? <a href={meal.source_url} target="_blank" rel="noreferrer">{meal.title}</a>
            : meal.title}
        </h3>
        <div className="mp-meal-meta">
          {meal.ready_in_minutes && <span>⏱ {meal.ready_in_minutes} min</span>}
          {meal.servings && <span>🍽 {meal.servings} serving{meal.servings !== 1 ? "s" : ""}</span>}
        </div>
        <div className="mp-meal-macros">
          <span className="mp-macro mp-macro--cal">{meal.calories} kcal</span>
          <span className="mp-macro mp-macro--p">{meal.protein_g}g P</span>
          <span className="mp-macro mp-macro--c">{meal.carbs_g}g C</span>
          <span className="mp-macro mp-macro--f">{meal.fat_g}g F</span>
        </div>
      </div>
    </div>
  );
}

// ─── Main component ───────────────────────────────────────

export default function MealPlanner({ userProfile, onBack, onUpgrade }: MealPlannerProps) {
  const [plan,       setPlan]       = useState<WeeklyPlan | null>(null);
  const [loading,    setLoading]    = useState(false);
  const [error,      setError]      = useState("");
  const [activeDay,  setActiveDay]  = useState(0);
  const [activeTab,  setActiveTab]  = useState<"plan" | "shopping">("plan");
  const [diet,       setDiet]       = useState("");
  const [checked,    setChecked]    = useState<Set<string>>(new Set());

  // Show paywall if user is not premium
  if (!userProfile?.is_premium) {
    return <Paywall onBack={onBack} onUpgrade={onUpgrade} />;
  }

  const generatePlan = useCallback(async () => {
    setLoading(true);
    setError("");
    setChecked(new Set());
    try {
      const token  = localStorage.getItem("token");
      const params = new URLSearchParams();
      if (diet) params.set("diet", diet);
      const res = await fetch(`/mealplan/weekly?${params}`, {
        headers: { Authorization: `Bearer ${token ?? ""}` },
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail ?? "Failed to generate plan");
      }
      const data: WeeklyPlan = await res.json();
      setPlan(data);
      setActiveDay(0);
      setActiveTab("plan");
    } catch (e: any) {
      setError(e.message ?? "Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  }, [diet]);

  const toggleCheck = (key: string) => {
    setChecked(prev => {
      const next = new Set(prev);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    });
  };

  const today = new Date();
  const targetKcal = userProfile?.uses_custom_goals
    ? userProfile?.custom_kcal
    : userProfile?.target_kcal;

  return (
    <div className="mp-root">
      <div className="mp-container">

        {/* Header */}
        <header className="mp-header">
          <button className="mp-back-btn" onClick={onBack}>← Back</button>
          <div>
            <h1 className="mp-title">Weekly Meal Planner</h1>
            {targetKcal && (
              <p className="mp-subtitle">Based on your {Math.round(targetKcal)} kcal/day goal</p>
            )}
          </div>
        </header>

        {/* Controls */}
        <div className="mp-controls">
          <select
            className="mp-diet-select"
            value={diet}
            onChange={e => setDiet(e.target.value)}
            disabled={loading}
          >
            {DIET_OPTIONS.map(o => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
          <button
            className="mp-generate-btn"
            onClick={generatePlan}
            disabled={loading}
          >
            {loading ? "Generating…" : plan ? "🔄 Regenerate" : "✨ Generate Plan"}
          </button>
        </div>

        {error && <p className="mp-error">{error}</p>}

        {/* Empty state */}
        {!plan && !loading && (
          <div className="mp-empty">
            <p className="mp-empty-emoji">🗓</p>
            <p className="mp-empty-text">
              Hit <strong>Generate Plan</strong> to get your personalised week of meals.
            </p>
          </div>
        )}

        {/* Loading skeleton */}
        {loading && (
          <div className="mp-loading">
            <div className="mp-spinner" />
            <p>Building your meal plan…</p>
          </div>
        )}

        {/* Plan content */}
        {plan && !loading && (
          <>
            {/* Main tabs */}
            <div className="mp-tabs">
              <button
                className={`mp-tab${activeTab === "plan" ? " mp-tab--active" : ""}`}
                onClick={() => setActiveTab("plan")}
              >
                🗓 Meal Plan
              </button>
              <button
                className={`mp-tab${activeTab === "shopping" ? " mp-tab--active" : ""}`}
                onClick={() => setActiveTab("shopping")}
              >
                🛒 Shopping List
              </button>
            </div>

            {/* ── Meal Plan tab ── */}
            {activeTab === "plan" && (
              <>
                {/* Day selector */}
                <div className="mp-days">
                  {plan.week.map((d, i) => (
                    <button
                      key={d.day}
                      className={`mp-day-btn${activeDay === i ? " mp-day-btn--active" : ""}`}
                      onClick={() => setActiveDay(i)}
                    >
                      <span className="mp-day-short">{DAYS_SHORT[i]}</span>
                      <span className="mp-day-kcal">{d.total_calories} kcal</span>
                    </button>
                  ))}
                </div>

                {/* Day meals */}
                <div className="mp-day-meals">
                  {(["breakfast", "lunch", "dinner", "snack"] as const).map(type => (
                    <MealCard
                      key={type}
                      type={type}
                      meal={plan.week[activeDay].meals[type]}
                    />
                  ))}
                </div>
              </>
            )}

            {/* ── Shopping List tab ── */}
            {activeTab === "shopping" && (
              <div className="mp-shopping">
                <p className="mp-shopping-count">
                  {plan.shopping_list.length} items for the week
                  {checked.size > 0 && ` · ${checked.size} checked off`}
                </p>
                <ul className="mp-shopping-list">
                  {plan.shopping_list.map((item, idx) => {
                    const key = `${item.name}-${item.unit}-${idx}`;
                    const done = checked.has(key);
                    return (
                      <li
                        key={key}
                        className={`mp-shopping-item${done ? " mp-shopping-item--done" : ""}`}
                        onClick={() => toggleCheck(key)}
                      >
                        <span className="mp-check">{done ? "✅" : "☐"}</span>
                        <span className="mp-shopping-name">{item.name}</span>
                        <span className="mp-shopping-amount">
                          {item.amount} {item.unit}
                        </span>
                      </li>
                    );
                  })}
                </ul>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
