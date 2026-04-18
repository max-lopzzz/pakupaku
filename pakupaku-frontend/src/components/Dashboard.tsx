import { useState, useEffect, useRef, useCallback } from "react";
import "./Dashboard.css";
import { round0, round1 } from "../utils/format";
import HealthNotesCard from "./HealthNotesCard";

// ─── Nutrient extraction from Spoonacular detail response ─────────────────────

function extractNutrientsFromDetail(detail: any): Record<string, number | null> {
  return {
    calories:   detail.calories   ?? null,
    protein_g:  detail.protein_g  ?? null,
    fat_g:      detail.fat_g      ?? null,
    carbs_g:    detail.carbs_g    ?? null,
  };
}

const UNIT_TO_G: Record<string, number> = { g: 1, ml: 1, oz: 28.3495, cup: 240, tbsp: 15, tsp: 5 };
const STANDARD_UNITS = ["g", "ml", "oz", "cup", "tbsp", "tsp"];

// ─── Food suggestion type ─────────────────────────────────

interface FoodSuggestion {
  spoonacular_id:    number;
  description:       string;
  calories_per_100g: number | null;
  protein_per_100g:  number | null;
  fat_per_100g:      number | null;
  carbs_per_100g:    number | null;
}

const STANDARD_UNIT_SET = new Set(STANDARD_UNITS);

function toGrams(amount: string, unit: string, portionsMap: Record<string, number> = {}): number {
  const conv = { ...UNIT_TO_G, ...portionsMap };
  return (parseFloat(amount) || 0) * (conv[unit] ?? 1);
}

// ─── Types ────────────────────────────────────────────────

interface NutritionData {
  calories: {
    consumed: number;
    goal: number;
  };
  protein: {
    consumed: number;
    goal: number;
  };
  carbs: {
    consumed: number;
    goal: number;
  };
  fat: {
    consumed: number;
    goal: number;
  };
}

type MealCategory = "breakfast" | "lunch" | "dinner" | "snacks";

interface Meal {
  id:        string;
  name:      string;
  time:      string;       // display string e.g. "02:30 PM"
  logged_at: string;       // raw ISO timestamp for editing
  category:  MealCategory;
  calories:  number;
  protein:   number;
  carbs:     number;
  fat:       number;
}

// Proportions must sum to 1.0
const MEAL_PROPORTIONS: { key: MealCategory; label: string; pct: number }[] = [
  { key: "breakfast", label: "Breakfast", pct: 0.25 },
  { key: "lunch",     label: "Lunch",     pct: 0.30 },
  { key: "dinner",    label: "Dinner",    pct: 0.35 },
  { key: "snacks",    label: "Snacks",    pct: 0.10 },
];

interface Recipe {
  id: string;
  name: string;
  total_calories: number;
  total_protein_g: number;
  total_fat_g: number;
  total_carbs_g: number;
}

interface BodyMeasurement {
  id:           string;
  measured_at:  string;
  weight_kg:    number | null;
  height_cm:    number | null;
  waist_cm:     number | null;
  neck_cm:      number | null;
  hip_cm:       number | null;
  body_fat_pct: number | null;
}

interface DashboardProps {
  nutritionData: NutritionData;
  userProfile: any;
  onOpenRecipeBuilder: () => void;
  onOpenMealPlanner:   () => void;
}

// ─── FoodLogInput component ───────────────────────────────

interface FoodLogInputProps {
  category: MealCategory;
  logDate:  string;
  onLogged: () => void;
}

function FoodLogInput({ category, logDate, onLogged }: FoodLogInputProps) {
  const [query, setQuery]             = useState("");
  const [suggestions, setSuggestions] = useState<FoodSuggestion[]>([]);
  const [showDropdown, setShowDropdown] = useState(false);
  const [selected, setSelected]       = useState<FoodSuggestion | null>(null);
  const [portionsMap, setPortionsMap] = useState<Record<string, number>>({});
  const [amount, setAmount]           = useState("100");
  const [unit, setUnit]               = useState("g");
  const [logging, setLogging]         = useState(false);
  const [error, setError]             = useState("");
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const wrapRef     = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node))
        setShowDropdown(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const handleQueryChange = (value: string) => {
    setQuery(value);
    setSelected(null);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (value.trim().length < 2) { setSuggestions([]); setShowDropdown(false); return; }
    debounceRef.current = setTimeout(async () => {
      try {
        const token = localStorage.getItem("token");
        const res = await fetch(
          `/foods/search?query=${encodeURIComponent(value.trim())}&page_size=50`,
          { headers: { Authorization: `Bearer ${token ?? ""}` } }
        );
        if (!res.ok) return;
        const data = await res.json();
        const results: FoodSuggestion[] = (data.results ?? [])
          .map((f: any) => ({
            spoonacular_id:    f.id,
            description:       f.name,
            calories_per_100g: null,
            protein_per_100g:  null,
            fat_per_100g:      null,
            carbs_per_100g:    null,
          }));
        setSuggestions(results);
        setShowDropdown(results.length > 0);
      } catch { /* ignore */ }
    }, 350);
  };

  const selectFood = async (food: FoodSuggestion) => {
    setQuery(food.description);
    setSelected(food);
    setSuggestions([]);
    setShowDropdown(false);

    const token   = localStorage.getItem("token");
    const headers = { Authorization: `Bearer ${token ?? ""}` };

    try {
      const res = await fetch(`/foods/${food.spoonacular_id}`, { headers });
      if (res.ok) {
        const detail = await res.json();

        // Update the selected food with nutrition from detail
        const withNutrition: FoodSuggestion = {
          ...food,
          calories_per_100g: detail.calories  ?? null,
          protein_per_100g:  detail.protein_g ?? null,
          fat_per_100g:      detail.fat_g     ?? null,
          carbs_per_100g:    detail.carbs_g   ?? null,
        };
        setSelected(withNutrition);

        // Build portions map from detail response
        const pm: Record<string, number> = {};
        for (const p of detail.portions ?? []) {
          if (p.unit && p.grams_per_unit) pm[p.unit] = p.grams_per_unit;
        }
        setPortionsMap(pm);

        const natural = Object.keys(pm).filter(u => !STANDARD_UNIT_SET.has(u));
        if (natural.length > 0) { setUnit(natural[0]); setAmount("1"); }
        else { setUnit("g"); setAmount("100"); }
      }
    } catch { /* non-fatal — user can still log in grams */ }
  };

  const handleLog = async () => {
    if (!selected) { setError("Select a food first."); return; }
    if (!amount.trim() || parseFloat(amount) <= 0) { setError("Enter a valid amount."); return; }
    setError("");
    setLogging(true);
    const amount_g = toGrams(amount, unit, portionsMap);
    const sc = (v: number | null) => v != null ? Math.round((v * amount_g / 100) * 10) / 10 : 0;
    const token = localStorage.getItem("token");
    try {
      const res = await fetch("/logs", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token ?? ""}` },
        body: JSON.stringify({
          spoonacular_id: selected.spoonacular_id,
          food_name:      selected.description,
          amount_g,
          calories:  sc(selected.calories_per_100g),
          protein_g: sc(selected.protein_per_100g),
          carbs_g:   sc(selected.carbs_per_100g),
          fat_g:     sc(selected.fat_per_100g),
          meal:      category,
          log_date:  logDate,
        }),
      });
      if (!res.ok) throw new Error();
      setQuery(""); setSelected(null); setAmount("100"); setUnit("g"); setPortionsMap({});
      onLogged();
    } catch {
      setError("Failed to log food.");
    } finally {
      setLogging(false);
    }
  };

  const allUnits = [
    ...Object.keys(portionsMap).filter(u => !STANDARD_UNIT_SET.has(u)),
    ...STANDARD_UNITS,
  ];

  return (
    <div className="food-log-input" ref={wrapRef}>
      <div className="food-search-wrap">
        <input
          type="text"
          placeholder="Search food…"
          value={query}
          onChange={e => handleQueryChange(e.target.value)}
          onFocus={() => suggestions.length > 0 && setShowDropdown(true)}
          autoComplete="off"
          className="food-search-input"
        />
        {showDropdown && (
          <ul className="food-autocomplete-dropdown">
            {suggestions.map(f => (
              <li
                key={f.spoonacular_id}
                onMouseDown={e => { e.preventDefault(); selectFood(f); }}
                className="food-autocomplete-item"
              >
                <span className="food-autocomplete-name">{f.description}</span>
                {f.calories_per_100g != null && (
                  <span className="food-autocomplete-kcal">
                    {Math.round(f.calories_per_100g)} kcal/100g
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
      {selected && (
        <div className="food-amount-row">
          <input
            type="number"
            min="0"
            step="any"
            value={amount}
            onChange={e => setAmount(e.target.value)}
            className="food-amount-input"
          />
          <select value={unit} onChange={e => setUnit(e.target.value)} className="food-unit-select">
            {allUnits.map(u => <option key={u} value={u}>{u}</option>)}
          </select>
          {selected.calories_per_100g != null && (
            <span className="food-kcal-preview">
              ≈ {Math.round(selected.calories_per_100g * toGrams(amount, unit, portionsMap) / 100)} kcal
            </span>
          )}
        </div>
      )}
      {error && <p className="food-log-error">{error}</p>}
      <button
        type="button"
        onClick={handleLog}
        disabled={!selected || logging}
        className="food-log-button"
      >
        {logging ? "Logging…" : "Log food"}
      </button>
    </div>
  );
}

// ─── CustomFoodInput component ────────────────────────────

interface CustomFoodInputProps {
  category: MealCategory;
  logDate:  string;
  onLogged: () => void;
}

function CustomFoodInput({ category, logDate, onLogged }: CustomFoodInputProps) {
  const [name,     setName]     = useState("");
  const [calories, setCalories] = useState("");
  const [protein,  setProtein]  = useState("");
  const [carbs,    setCarbs]    = useState("");
  const [fat,      setFat]      = useState("");
  const [logging,  setLogging]  = useState(false);
  const [error,    setError]    = useState("");

  const handleLog = async () => {
    if (!name.trim())                         { setError("Enter a food name."); return; }
    if (!calories || parseFloat(calories) < 0) { setError("Enter valid calories."); return; }
    setError("");
    setLogging(true);
    const token = localStorage.getItem("token");
    try {
      const res = await fetch("/logs", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token ?? ""}` },
        body: JSON.stringify({
          food_name: name.trim(),
          amount_g:  100,
          calories:  parseFloat(calories) || 0,
          protein_g: parseFloat(protein)  || 0,
          carbs_g:   parseFloat(carbs)    || 0,
          fat_g:     parseFloat(fat)      || 0,
          meal:      category,
          log_date:  logDate,
        }),
      });
      if (!res.ok) throw new Error();
      setName(""); setCalories(""); setProtein(""); setCarbs(""); setFat("");
      onLogged();
    } catch {
      setError("Failed to log food.");
    } finally {
      setLogging(false);
    }
  };

  return (
    <div className="custom-food-input">
      <input
        type="text"
        placeholder="Food name (e.g. Protein bar, Brand X)"
        value={name}
        onChange={e => setName(e.target.value)}
        className="custom-food-name"
      />
      <div className="custom-food-macros">
        <label className="custom-food-field">
          <span>Calories</span>
          <input type="number" min="0" step="any" placeholder="0"
            value={calories} onChange={e => setCalories(e.target.value)} />
        </label>
        <label className="custom-food-field">
          <span>Protein (g)</span>
          <input type="number" min="0" step="any" placeholder="0"
            value={protein} onChange={e => setProtein(e.target.value)} />
        </label>
        <label className="custom-food-field">
          <span>Carbs (g)</span>
          <input type="number" min="0" step="any" placeholder="0"
            value={carbs} onChange={e => setCarbs(e.target.value)} />
        </label>
        <label className="custom-food-field">
          <span>Fat (g)</span>
          <input type="number" min="0" step="any" placeholder="0"
            value={fat} onChange={e => setFat(e.target.value)} />
        </label>
      </div>
      {error && <p className="food-log-error">{error}</p>}
      <button
        type="button"
        onClick={handleLog}
        disabled={!name.trim() || !calories || logging}
        className="food-log-button"
      >
        {logging ? "Logging…" : "Log food"}
      </button>
    </div>
  );
}

// ─── Main component ───────────────────────────────────────

export default function Dashboard({ nutritionData, userProfile, onOpenRecipeBuilder, onOpenMealPlanner }: DashboardProps) {
  const [meals, setMeals] = useState<Meal[]>([]);
  const [recipes, setRecipes] = useState<Recipe[]>([]);
  const [selectedRecipe, setSelectedRecipe] = useState<{ [key in MealCategory]: string }>({
    breakfast: "",
    lunch: "",
    dinner: "",
    snacks: "",
  });
  const [selectedDate, setSelectedDate] = useState<string>(() => new Date().toISOString().slice(0, 10));
  const isToday = selectedDate === new Date().toISOString().slice(0, 10);

  // { id: mealId, value: "HH:MM" } while a time field is being edited
  const [editingTime, setEditingTime] = useState<{ id: string; value: string } | null>(null);

  const [addTab, setAddTab] = useState<{ [key in MealCategory]: "food" | "custom" | "recipe" }>({
    breakfast: "food",
    lunch: "food",
    dinner: "food",
    snacks: "food",
  });

  // Measurements
  const [measurements, setMeasurements] = useState<BodyMeasurement[]>([]);
  const [measWeight, setMeasWeight]     = useState("");
  const [measHeight, setMeasHeight]     = useState("");
  const [measWaist, setMeasWaist]       = useState("");
  const [measNeck, setMeasNeck]         = useState("");
  const [measHip, setMeasHip]           = useState("");
  const [measDate, setMeasDate]         = useState(() => new Date().toISOString().slice(0, 10));
  const [measError, setMeasError]       = useState("");
  const [measSaving, setMeasSaving]     = useState(false);
  const chartRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    const fetchRecipes = async () => {
      const token = localStorage.getItem("token");
      if (!token) {
        setRecipes([]);
        return;
      }

      try {
        const res = await fetch("/recipes", {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!res.ok) {
          console.error("Failed to fetch recipes:", res.status);
          setRecipes([]);
          return;
        }
        const fetchedRecipes = await res.json();
        setRecipes(Array.isArray(fetchedRecipes) ? fetchedRecipes : []);
      } catch (error) {
        console.error("Failed to fetch recipes:", error);
        setRecipes([]);
      }
    };

    fetchRecipes();
  }, []);

  useEffect(() => {
    const fetchLogs = async () => {
      const token = localStorage.getItem("token");
      if (!token) { setMeals([]); return; }
      try {
        const res = await fetch(`/logs?log_date=${selectedDate}`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!res.ok) { setMeals([]); return; }
        const logs = await res.json();
        if (!Array.isArray(logs)) { setMeals([]); return; }
        setMeals(logs.map((log: any) => ({
          id:        log.id,
          name:      log.food_name,
          logged_at: log.logged_at,
          time:      new Date(log.logged_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
          category:  (log.meal as MealCategory) || "snacks",
          calories:  log.calories  || 0,
          protein:   log.protein_g || 0,
          carbs:     log.carbs_g   || 0,
          fat:       log.fat_g     || 0,
        })));
      } catch { setMeals([]); }
    };
    fetchLogs();
  }, [selectedDate]);

  useEffect(() => {
    const fetchMeasurements = async () => {
      const token = localStorage.getItem("token");
      if (!token) return;
      try {
        const res = await fetch("/measurements", {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (res.ok) setMeasurements(await res.json());
      } catch { /* non-fatal */ }
    };
    fetchMeasurements();
  }, []);

  const handleLogMeasurement = async () => {
    setMeasError("");
    if (!measWeight && !measHeight && !measWaist && !measNeck && !measHip) {
      setMeasError("Enter at least one measurement.");
      return;
    }
    const token = localStorage.getItem("token");
    if (!token) return;
    setMeasSaving(true);
    try {
      const res = await fetch("/measurements", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          measured_at: measDate || undefined,
          weight_kg:   measWeight ? parseFloat(measWeight) : undefined,
          height_cm:   measHeight ? parseFloat(measHeight) : undefined,
          waist_cm:    measWaist  ? parseFloat(measWaist)  : undefined,
          neck_cm:     measNeck   ? parseFloat(measNeck)   : undefined,
          hip_cm:      measHip    ? parseFloat(measHip)    : undefined,
        }),
      });
      if (!res.ok) throw new Error();
      const saved: BodyMeasurement = await res.json();
      setMeasurements(prev => [...prev, saved].sort((a, b) =>
        a.measured_at.localeCompare(b.measured_at)
      ));
      setMeasWeight(""); setMeasHeight(""); setMeasWaist(""); setMeasNeck(""); setMeasHip("");
    } catch {
      setMeasError("Failed to save measurement.");
    } finally {
      setMeasSaving(false);
    }
  };

  const refreshLogs = useCallback(async () => {
    const token = localStorage.getItem("token");
    if (!token) return;
    try {
      const res = await fetch(`/logs?log_date=${selectedDate}`, { headers: { Authorization: `Bearer ${token}` } });
      if (!res.ok) return;
      const logs = await res.json();
      setMeals(logs.map((log: any) => ({
        id:       log.id,
        name:     log.food_name,
        time:     new Date(log.logged_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        category: (log.meal as MealCategory) || "snacks",
        calories: log.calories  || 0,
        protein:  log.protein_g || 0,
        carbs:    log.carbs_g   || 0,
        fat:      log.fat_g     || 0,
      })));
    } catch { /* non-fatal */ }
  }, [selectedDate]);

  const handleTimeEdit = useCallback(async (mealId: string) => {
    if (!editingTime || editingTime.id !== mealId) { setEditingTime(null); return; }
    const token = localStorage.getItem("token");
    if (!token) { setEditingTime(null); return; }
    try {
      // Combine the currently-viewed date with the newly chosen HH:MM
      const newLoggedAt = new Date(`${selectedDate}T${editingTime.value}:00`).toISOString();
      const res = await fetch(`/logs/${mealId}`, {
        method:  "PATCH",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body:    JSON.stringify({ logged_at: newLoggedAt }),
      });
      if (res.ok) {
        setMeals(prev => prev.map(m =>
          m.id === mealId
            ? { ...m, logged_at: newLoggedAt, time: new Date(newLoggedAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) }
            : m
        ));
      }
    } catch { /* non-fatal */ }
    setEditingTime(null);
  }, [editingTime, selectedDate]);

  const handleAddRecipe = async (category: MealCategory) => {
    const recipeId = selectedRecipe[category];
    if (!recipeId) return;
    const recipe = recipes.find((r) => r.id === recipeId);
    if (!recipe) return;
    const token = localStorage.getItem("token");
    if (!token) return;
    try {
      const res = await fetch("/logs", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          recipe_id: recipeId,
          food_name: recipe.name,
          amount_g:  100,
          calories:  recipe.total_calories,
          protein_g: recipe.total_protein_g,
          carbs_g:   recipe.total_carbs_g,
          fat_g:     recipe.total_fat_g,
          meal:      category,
          log_date:  selectedDate,
        }),
      });
      if (res.ok) {
        await refreshLogs();
        setSelectedRecipe(prev => ({ ...prev, [category]: "" }));
      }
    } catch (error) {
      console.error("Failed to add recipe to meal:", error);
    }
  };

  const categoryConsumed = (category: MealCategory) =>
    meals
      .filter((meal) => meal.category === category)
      .reduce((sum, meal) => sum + meal.calories, 0);

  const totalGoal = nutritionData.calories.goal || 2000;
  const CATEGORY_OPTIONS = MEAL_PROPORTIONS.map(c => ({
    ...c,
    goal: Math.round(totalGoal * c.pct),
  }));

  const mealsByCategory = CATEGORY_OPTIONS.map((category) => ({
    ...category,
    meals: meals.filter((meal) => meal.category === category.key),
    consumed: categoryConsumed(category.key),
  }));

  const totalConsumed = meals.reduce(
    (acc, meal) => ({
      calories: acc.calories + meal.calories,
      protein: acc.protein + meal.protein,
      carbs: acc.carbs + meal.carbs,
      fat: acc.fat + meal.fat,
    }),
    { calories: 0, protein: 0, carbs: 0, fat: 0 }
  );

  const progressPercent = (macro: keyof NutritionData) => {
    const consumed = totalConsumed[macro];
    const goal = nutritionData[macro].goal;
    return Math.min((consumed / goal) * 100, 100);
  };

  return (
    <div className="dashboard-root" style={{
      backgroundImage: `url(${process.env.PUBLIC_URL}/polka_dots.png)`,
      backgroundSize: '280px 280px',
      backgroundRepeat: 'repeat'
    }}>
      <div className="dashboard-container">
        {/* Header */}
        <header className="dashboard-header">
          <div>
            <h1 className="dashboard-title">Welcome back! 👋</h1>
            <p className="dashboard-subtitle">Track your nutrition journey</p>
          </div>
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <button type="button" className="secondary-button" onClick={onOpenMealPlanner}>
              🗓 Meal Plan
            </button>
            <button type="button" className="secondary-button" onClick={onOpenRecipeBuilder}>
              Create recipe
            </button>
          </div>
        </header>

        {/* Date navigation */}
        <div className="date-nav">
          <button
            type="button"
            className="date-nav-btn"
            onClick={() => {
              const d = new Date(selectedDate);
              d.setDate(d.getDate() - 1);
              setSelectedDate(d.toISOString().slice(0, 10));
            }}
          >
            ←
          </button>
          <input
            type="date"
            className="date-nav-input"
            value={selectedDate}
            max={new Date().toISOString().slice(0, 10)}
            onChange={e => setSelectedDate(e.target.value)}
          />
          <button
            type="button"
            className="date-nav-btn"
            disabled={isToday}
            onClick={() => {
              const d = new Date(selectedDate);
              d.setDate(d.getDate() + 1);
              setSelectedDate(d.toISOString().slice(0, 10));
            }}
          >
            →
          </button>
          {!isToday && (
            <button
              type="button"
              className="date-nav-today"
              onClick={() => setSelectedDate(new Date().toISOString().slice(0, 10))}
            >
              today
            </button>
          )}
        </div>

        {/* Overall calorie progress */}
        <section className="overall-calorie-section">
          <h2 className="section-title">Calorie Progress</h2>
          <div className="overall-progress-card">
            <div className="overall-progress-label">
              <span>Today</span>
              <strong>{round0(totalConsumed.calories)} / {round0(nutritionData.calories.goal)} cal</strong>
            </div>
            <div className="overall-progress-bar">
              <div
                className="overall-progress-fill"
                style={{ width: `${progressPercent('calories')}%` }}
              />
            </div>
          </div>
        </section>

        {/* Nutrition Overview */}
        <section className="nutrition-overview">
          <h2 className="section-title">Macro Progress</h2>
          <div className="nutrition-grid">
            <div className="nutrition-card">
              <div className="macro-header">
                <span className="macro-name">Calories</span>
                <span className="macro-values">
                  {round0(totalConsumed.calories)} / {round0(nutritionData.calories.goal)}
                </span>
              </div>
              <div className="progress-bar">
                <div
                  className="progress-fill calories"
                  style={{ width: `${progressPercent('calories')}%` }}
                />
              </div>
            </div>

            <div className="nutrition-card">
              <div className="macro-header">
                <span className="macro-name">Protein</span>
                <span className="macro-values">
                  {round0(totalConsumed.protein)}g / {round0(nutritionData.protein.goal)}g
                </span>
              </div>
              <div className="progress-bar">
                <div
                  className="progress-fill protein"
                  style={{ width: `${progressPercent('protein')}%` }}
                />
              </div>
            </div>

            <div className="nutrition-card">
              <div className="macro-header">
                <span className="macro-name">Carbs</span>
                <span className="macro-values">
                  {round0(totalConsumed.carbs)}g / {round0(nutritionData.carbs.goal)}g
                </span>
              </div>
              <div className="progress-bar">
                <div
                  className="progress-fill carbs"
                  style={{ width: `${progressPercent('carbs')}%` }}
                />
              </div>
            </div>

            <div className="nutrition-card">
              <div className="macro-header">
                <span className="macro-name">Fat</span>
                <span className="macro-values">
                  {round0(totalConsumed.fat)}g / {round0(nutritionData.fat.goal)}g
                </span>
              </div>
              <div className="progress-bar">
                <div
                  className="progress-fill fat"
                  style={{ width: `${progressPercent('fat')}%` }}
                />
              </div>
            </div>
          </div>
        </section>

        {/* Body Statistics */}
        <section className="body-stats-section">
          <h2 className="section-title">Body Statistics</h2>
          {(() => {
            const latest = measurements.length > 0 ? measurements[measurements.length - 1] : null;

            // Age: calculate from birthday if available, otherwise fall back to stored age
            let age: string = "N/A";
            if (userProfile?.birthday) {
              const dob   = new Date(userProfile.birthday);
              const today = new Date();
              let a = today.getFullYear() - dob.getFullYear();
              const m = today.getMonth() - dob.getMonth();
              if (m < 0 || (m === 0 && today.getDate() < dob.getDate())) a--;
              age = String(a);
            } else if (userProfile?.age) {
              age = String(userProfile.age);
            }

            const lastWith = <K extends keyof BodyMeasurement>(key: K) =>
              [...measurements].reverse().find(m => m[key] != null)?.[key] ?? null;

            // Height: from latest measurement with height, or onboarding value
            const height = lastWith("height_cm") ?? userProfile?.height_cm ?? null;

            // Weight: from latest measurement, then fall back to onboarding value
            const weight = lastWith("weight_kg") ?? userProfile?.weight_kg ?? null;

            // Body fat: from latest measurement with body_fat_pct, or onboarding value
            const bf = lastWith("body_fat_pct") ?? userProfile?.body_fat_pct ?? null;

            return (
              <div className="body-stats-grid">
                <div className="stat-card">
                  <span className="stat-label">Weight</span>
                  <span className="stat-value">{weight != null ? `${round1(weight)} kg` : "N/A"}</span>
                </div>
                <div className="stat-card">
                  <span className="stat-label">Height</span>
                  <span className="stat-value">{height != null ? `${round1(height)} cm` : "N/A"}</span>
                </div>
                <div className="stat-card">
                  <span className="stat-label">Age</span>
                  <span className="stat-value">{age}</span>
                </div>
                <div className="stat-card">
                  <span className="stat-label">Body Fat %</span>
                  <span className="stat-value">{bf != null ? `${round1(bf)}%` : "N/A"}</span>
                </div>
              </div>
            );
          })()}

          {/* Weight chart */}
          <div className="weight-timeline">
            <h3>Weight Timeline</h3>
            {(() => {
              const pts = measurements.filter(m => m.weight_kg != null);
              if (pts.length === 0) {
                return <p className="timeline-empty">No weight entries yet. Log one below.</p>;
              }
              const W = 560, H = 120, PAD = { t: 12, r: 16, b: 28, l: 44 };
              const weights = pts.map(p => p.weight_kg as number);
              const minW = Math.min(...weights), maxW = Math.max(...weights);
              const range = maxW - minW || 1;
              const xStep = pts.length > 1
                ? (W - PAD.l - PAD.r) / (pts.length - 1)
                : (W - PAD.l - PAD.r) / 2;
              const toX = (i: number) => PAD.l + (pts.length > 1 ? i * xStep : (W - PAD.l - PAD.r) / 2);
              const toY = (w: number) => PAD.t + (H - PAD.t - PAD.b) * (1 - (w - minW) / range);
              const polyline = pts.map((p, i) => `${toX(i)},${toY(p.weight_kg as number)}`).join(" ");
              const yTicks = [minW, (minW + maxW) / 2, maxW];
              return (
                <svg ref={chartRef} viewBox={`0 0 ${W} ${H}`} className="weight-chart-svg">
                  {/* Y grid + labels */}
                  {yTicks.map((v, i) => {
                    const y = toY(v);
                    return (
                      <g key={i}>
                        <line x1={PAD.l} y1={y} x2={W - PAD.r} y2={y} stroke="#eaf5f3" strokeWidth="1" />
                        <text x={PAD.l - 4} y={y + 4} textAnchor="end" fontSize="9" fill="#8a6060">
                          {v.toFixed(1)}
                        </text>
                      </g>
                    );
                  })}
                  {/* Line */}
                  <polyline points={polyline} fill="none" stroke="#badfdb" strokeWidth="2.5" strokeLinejoin="round" />
                  {/* Dots + x labels */}
                  {pts.map((p, i) => {
                    const x = toX(i), y = toY(p.weight_kg as number);
                    const label = p.measured_at.slice(5); // MM-DD
                    return (
                      <g key={p.id}>
                        <circle cx={x} cy={y} r="4" fill="#ffbdbd" />
                        <text x={x} y={H - PAD.b + 12} textAnchor="middle" fontSize="9" fill="#8a6060">
                          {label}
                        </text>
                      </g>
                    );
                  })}
                </svg>
              );
            })()}
          </div>

          {/* Log measurement form */}
          <div className="measurement-form">
            <h3>Log measurement</h3>
            <div className="measurement-row">
              <label className="measurement-field">
                <span>Date</span>
                <input type="date" value={measDate} onChange={e => setMeasDate(e.target.value)} />
              </label>
              <label className="measurement-field">
                <span>Weight (kg)</span>
                <input type="number" min="0" step="0.1" placeholder="e.g. 72.5"
                  value={measWeight} onChange={e => setMeasWeight(e.target.value)} />
              </label>
              <label className="measurement-field">
                <span>Height (cm)</span>
                <input type="number" min="0" step="0.1" placeholder={userProfile?.height_cm ? `${userProfile.height_cm} (onboarding)` : "e.g. 168"}
                  value={measHeight} onChange={e => setMeasHeight(e.target.value)} />
              </label>
              <label className="measurement-field">
                <span>Waist (cm)</span>
                <input type="number" min="0" step="0.1" placeholder="e.g. 80"
                  value={measWaist} onChange={e => setMeasWaist(e.target.value)} />
              </label>
              <label className="measurement-field">
                <span>Neck (cm)</span>
                <input type="number" min="0" step="0.1" placeholder="e.g. 38"
                  value={measNeck} onChange={e => setMeasNeck(e.target.value)} />
              </label>
              <label className="measurement-field">
                <span>Hip (cm)</span>
                <input type="number" min="0" step="0.1" placeholder="e.g. 95"
                  value={measHip} onChange={e => setMeasHip(e.target.value)} />
              </label>
            </div>
            {measError && <p className="measurement-error">{measError}</p>}
            <button type="button" className="measurement-save-button"
              onClick={handleLogMeasurement} disabled={measSaving}>
              {measSaving ? "Saving…" : "Save measurement"}
            </button>
          </div>
        </section>

        <HealthNotesCard conditions={userProfile?.metabolic_conditions ?? []} />

        <section className="category-section">
          <h2 className="section-title">Meals by Category</h2>
          <div className="category-grid">
            {mealsByCategory.map((category) => (
              <div key={category.key} className="category-card">
                <div className="category-header">
                  <div>
                    <h3>{category.label}</h3>
                    <p>{round0(category.consumed)} / {round0(category.goal)} cal</p>
                  </div>
                  <div className="category-progress-bar">
                    <div
                      className="category-progress-fill"
                      style={{ width: `${Math.min((category.consumed / category.goal) * 100, 100)}%` }}
                    />
                  </div>
                </div>
                {category.meals.length === 0 ? (
                  <div className="category-empty">No {category.label.toLowerCase()} logged yet.</div>
                ) : (
                  <div className="category-meals">
                    {category.meals.map((meal) => (
                      <div key={meal.id} className="meal-card">
                        <div className="meal-header">
                          <h3 className="meal-name">{meal.name}</h3>
                          {editingTime?.id === meal.id ? (
                            <input
                              type="time"
                              className="meal-time-input"
                              value={editingTime.value}
                              autoFocus
                              onChange={e => setEditingTime({ id: meal.id, value: e.target.value })}
                              onBlur={() => handleTimeEdit(meal.id)}
                              onKeyDown={e => {
                                if (e.key === "Enter")  handleTimeEdit(meal.id);
                                if (e.key === "Escape") setEditingTime(null);
                              }}
                            />
                          ) : (
                            <span
                              className="meal-time meal-time--editable"
                              title="Click to edit time"
                              onClick={() => {
                                const d = new Date(meal.logged_at);
                                const hh = String(d.getHours()).padStart(2, "0");
                                const mm = String(d.getMinutes()).padStart(2, "0");
                                setEditingTime({ id: meal.id, value: `${hh}:${mm}` });
                              }}
                            >
                              {meal.time} ✎
                            </span>
                          )}
                        </div>
                        <div className="meal-macros">
                          <span className="macro-item">{round0(meal.calories)} cal</span>
                          <span className="macro-item">{round0(meal.protein)}g P</span>
                          <span className="macro-item">{round0(meal.carbs)}g C</span>
                          <span className="macro-item">{round0(meal.fat)}g F</span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
                <div className="add-food-form">
                  <div className="add-food-tabs">
                    <button
                      type="button"
                      className={`add-tab-btn${addTab[category.key] === "food" ? " active" : ""}`}
                      onClick={() => setAddTab(prev => ({ ...prev, [category.key]: "food" }))}
                    >
                      Food
                    </button>
                    <button
                      type="button"
                      className={`add-tab-btn${addTab[category.key] === "custom" ? " active" : ""}`}
                      onClick={() => setAddTab(prev => ({ ...prev, [category.key]: "custom" }))}
                    >
                      Custom
                    </button>
                    <button
                      type="button"
                      className={`add-tab-btn${addTab[category.key] === "recipe" ? " active" : ""}`}
                      onClick={() => setAddTab(prev => ({ ...prev, [category.key]: "recipe" }))}
                    >
                      Recipe
                    </button>
                  </div>

                  {addTab[category.key] === "food" ? (
                    <FoodLogInput category={category.key} logDate={selectedDate} onLogged={refreshLogs} />
                  ) : addTab[category.key] === "custom" ? (
                    <CustomFoodInput category={category.key} logDate={selectedDate} onLogged={refreshLogs} />
                  ) : (
                    <div className="recipe-log-form">
                      <select
                        value={selectedRecipe[category.key]}
                        onChange={(e) => setSelectedRecipe(prev => ({ ...prev, [category.key]: e.target.value }))}
                      >
                        <option value="">Select a recipe…</option>
                        {recipes.map((recipe) => (
                          <option key={recipe.id} value={recipe.id}>
                            {recipe.name} ({round0(recipe.total_calories)} cal)
                          </option>
                        ))}
                      </select>
                      <button type="button" onClick={() => handleAddRecipe(category.key)}>
                        Add Recipe
                      </button>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}