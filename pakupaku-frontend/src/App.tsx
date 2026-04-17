import { useState, useEffect, useRef } from "react";
import Login from "./components/Login";
import Onboarding from "./components/Onboarding";
import Dashboard from "./components/Dashboard";
import RecipeBuilder from "./components/RecipeBuilder";
import MealPlanner from "./components/MealPlanner";

interface NutritionData {
  calories: { consumed: number; goal: number };
  protein:  { consumed: number; goal: number };
  carbs:    { consumed: number; goal: number };
  fat:      { consumed: number; goal: number };
}

type AppView = "login" | "verifyEmail" | "onboarding" | "dashboard" | "recipeBuilder" | "mealPlanner";

// ─── Helpers ─────────────────────────────────────────────

function applyUserProfile(user: any, setNutritionData: (d: NutritionData) => void) {
  if (user.uses_custom_goals) {
    setNutritionData({
      calories: { consumed: 0, goal: user.custom_kcal    || 2000 },
      protein:  { consumed: 0, goal: user.custom_protein || 150  },
      carbs:    { consumed: 0, goal: user.custom_carbs   || 250  },
      fat:      { consumed: 0, goal: user.custom_fat     || 67   },
    });
  } else if (user.target_kcal) {
    setNutritionData({
      calories: { consumed: 0, goal: user.target_kcal   },
      protein:  { consumed: 0, goal: user.protein_g || 150 },
      carbs:    { consumed: 0, goal: user.carbs_g   || 250 },
      fat:      { consumed: 0, goal: user.fat_g     || 67  },
    });
  }
}

function viewForUser(user: any): AppView {
  if (!user.email_verified)                          return "verifyEmail";
  if (user.target_kcal || user.uses_custom_goals)   return "dashboard";
  return "onboarding";
}

// ─── App ─────────────────────────────────────────────────

function App() {
  const [view, setView]               = useState<AppView>("login");
  const [nutritionData, setNutritionData] = useState<NutritionData>({
    calories: { consumed: 0, goal: 2000 },
    protein:  { consumed: 0, goal: 150  },
    carbs:    { consumed: 0, goal: 250  },
    fat:      { consumed: 0, goal: 67   },
  });
  const [userProfile, setUserProfile] = useState<any>(null);
  const [justVerified, setJustVerified] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ── Fetch user and route ──────────────────────────────
  const loadUser = async (): Promise<any | null> => {
    const token = localStorage.getItem("token");
    if (!token) return null;
    const res = await fetch("/users/me", {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) {
      localStorage.removeItem("token");
      return null;
    }
    return res.json();
  };

  const routeUser = (user: any) => {
    setUserProfile(user);
    applyUserProfile(user, setNutritionData);
    setView(viewForUser(user));
  };

  // ── Initial load ──────────────────────────────────────
  useEffect(() => {
    // Check for ?verified= redirect from email link
    const params = new URLSearchParams(window.location.search);
    const v = params.get("verified");
    if (v === "true")  setJustVerified(true);
    if (v) window.history.replaceState({}, "", window.location.pathname);

    const token = localStorage.getItem("token");
    if (!token) { setView("login"); return; }

    loadUser()
      .then(user => { if (user) routeUser(user); else setView("login"); })
      .catch(() => setView("login"));
  }, []);

  // ── Poll while on verifyEmail view ────────────────────
  useEffect(() => {
    if (view !== "verifyEmail") {
      if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
      return;
    }
    pollRef.current = setInterval(async () => {
      const user = await loadUser().catch(() => null);
      if (user?.email_verified) {
        clearInterval(pollRef.current!);
        pollRef.current = null;
        routeUser(user);
      }
    }, 3000);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [view]);

  // ── Handlers ──────────────────────────────────────────
  const handleLoginSuccess = async () => {
    const user = await loadUser().catch(() => null);
    if (user) routeUser(user); else setView("login");
  };

  const handleOnboardingComplete = (data: any) => {
    setNutritionData({
      calories: { consumed: 0, goal: data.target_kcal || 2000 },
      protein:  { consumed: 0, goal: data.protein_g   || 150  },
      carbs:    { consumed: 0, goal: data.carbs_g     || 250  },
      fat:      { consumed: 0, goal: data.fat_g       || 67   },
    });
    setView("dashboard");
  };

  // ── Verify email gate view ────────────────────────────
  if (view === "verifyEmail") {
    return <VerifyEmailGate
      email={userProfile?.email ?? ""}
      justVerified={justVerified}
      onVerified={() => {
        setJustVerified(false);
        loadUser().then(u => { if (u) routeUser(u); });
      }}
    />;
  }

  if (view === "login") {
    return <Login onLoginSuccess={handleLoginSuccess} />;
  }

  if (view === "recipeBuilder") {
    return <RecipeBuilder onBack={() => setView("dashboard")} />;
  }

  if (view === "mealPlanner") {
    return <MealPlanner
      userProfile={userProfile}
      onBack={() => setView("dashboard")}
      onUpgrade={async () => {
        const u = await loadUser().catch(() => null);
        if (u) routeUser(u);
      }}
    />;
  }

  if (view === "dashboard") {
    return <Dashboard
      nutritionData={nutritionData}
      userProfile={userProfile}
      onOpenRecipeBuilder={() => setView("recipeBuilder")}
      onOpenMealPlanner={() => setView("mealPlanner")}
    />;
  }

  return <Onboarding onComplete={handleOnboardingComplete} />;
}

// ─── Verify Email Gate ────────────────────────────────────

function VerifyEmailGate({ email, justVerified, onVerified }: {
  email: string;
  justVerified: boolean;
  onVerified: () => void;
}) {
  const [resendState, setResendState] = useState<"idle" | "sending" | "sent" | "error">("idle");

  // If the page loaded with ?verified=true, proceed immediately
  useEffect(() => {
    if (justVerified) onVerified();
  }, [justVerified]);

  const handleResend = async () => {
    setResendState("sending");
    const token = localStorage.getItem("token");
    try {
      const res = await fetch("/auth/resend-verification", {
        method: "POST",
        headers: { Authorization: token ? `Bearer ${token}` : "" },
      });
      setResendState(res.ok ? "sent" : "error");
    } catch {
      setResendState("error");
    }
  };

  return (
    <div className="login-root">
      <div className="login-card">
        <h1 className="login-title">Check your inbox 📬</h1>
        <p className="login-subtitle">
          We sent a verification link to <strong>{email}</strong>.
          Please click it to continue.
        </p>
        <p className="login-subtitle" style={{ fontSize: "0.85rem", marginTop: "0.75rem", color: "#8a6060" }}>
          This page will unlock automatically once you verify.
        </p>
        <button
          className="submit-btn"
          style={{ marginTop: "1.5rem" }}
          onClick={handleResend}
          disabled={resendState === "sending" || resendState === "sent"}
        >
          {resendState === "sending" ? "Sending…"
            : resendState === "sent"  ? "Email sent! Check your inbox"
            : resendState === "error" ? "Failed — try again"
            : "Resend verification email"}
        </button>
        <p style={{ marginTop: "1rem", fontSize: "0.8rem", color: "#c8b4b4", textAlign: "center" }}>
          Check your spam folder if you don't see it.
        </p>
      </div>
    </div>
  );
}

export default App;
