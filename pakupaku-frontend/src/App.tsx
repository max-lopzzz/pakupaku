import { useState, useEffect, useRef } from "react";
import Login from "./components/Login";
import Onboarding from "./components/Onboarding";
import Dashboard from "./components/Dashboard";
import RecipeBuilder from "./components/RecipeBuilder";
import Settings from "./components/Settings";
import ResetPassword from "./components/ResetPassword";
import { apiFetch } from "./apiBase";

interface NutritionData {
  calories: { consumed: number; goal: number };
  protein:  { consumed: number; goal: number };
  carbs:    { consumed: number; goal: number };
  fat:      { consumed: number; goal: number };
}

type AppView = "login" | "verifyEmail" | "onboarding" | "dashboard" | "recipeBuilder" | "settings" | "resetPassword";

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
  const [resetToken, setResetToken] = useState("");
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ── Fetch user and route ──────────────────────────────
  const loadUser = async (): Promise<any | null> => {
    const token = localStorage.getItem("token");
    if (!token) return null;
    const res = await apiFetch("/users/me", {
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
  const didInitialLoad = useRef(false);
  useEffect(() => {
    // Guard against StrictMode's dev-only double-invocation: this effect
    // reads window.location.search and then mutates it (replaceState), so
    // a second invocation would see the already-stripped URL and silently
    // fall through to the wrong branch below, clobbering the view a first
    // invocation had already set from ?reset=/?verified=.
    if (didInitialLoad.current) return;
    didInitialLoad.current = true;

    // Check for ?verified= redirect from email link
    const params = new URLSearchParams(window.location.search);
    const v = params.get("verified");
    if (v === "true")  setJustVerified(true);
    if (v) window.history.replaceState({}, "", window.location.pathname);

    // Check for ?reset= redirect from the password-reset email link. This
    // is an unauthenticated flow — it doesn't matter whether a login
    // token exists, so it's handled before that check below.
    const resetTokenParam = params.get("reset");
    if (resetTokenParam) {
      window.history.replaceState({}, "", window.location.pathname);
      setResetToken(resetTokenParam);
      setView("resetPassword");
      return;
    }

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

  const handleOnboardingComplete = async () => {
    // Re-fetch rather than build nutritionData from the calculate
    // endpoint's response: that response has target_kcal/protein_g/etc.
    // but not weight_kg/height_cm/birthday/body_fat_pct, so userProfile
    // would stay stuck at its pre-onboarding (all-null) values and the
    // dashboard's Body Statistics would show N/A despite the user having
    // just entered all of it. routeUser() (same as login) picks up
    // everything onboarding just persisted, in one fetch.
    const user = await loadUser().catch(() => null);
    if (user) routeUser(user); else setView("login");
  };

  const handleLogout = () => {
    localStorage.removeItem("token");
    setUserProfile(null);
    setView("login");
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

  if (view === "resetPassword") {
    return <ResetPassword token={resetToken} onDone={() => setView("login")} />;
  }

  if (view === "login") {
    return <Login onLoginSuccess={handleLoginSuccess} />;
  }

  if (view === "recipeBuilder") {
    return <RecipeBuilder onBack={() => setView("dashboard")} />;
  }

  if (view === "dashboard") {
    return <Dashboard
      nutritionData={nutritionData}
      userProfile={userProfile}
      onOpenRecipeBuilder={() => setView("recipeBuilder")}
      onOpenSettings={() => setView("settings")}
    />;
  }

  if (view === "settings") {
    return <Settings
      userProfile={userProfile}
      onBack={() => setView("dashboard")}
      onLogout={handleLogout}
      onProfileUpdate={(updated: any) => setUserProfile(updated)}
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

  // If the page loaded with ?verified=true, proceed immediately. Only
  // justVerified should retrigger this — onVerified is a fresh closure
  // on every parent render, so including it would fire this on every
  // re-render instead of just the justVerified transition.
  useEffect(() => {
    if (justVerified) onVerified();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [justVerified]);

  const handleResend = async () => {
    setResendState("sending");
    const token = localStorage.getItem("token");
    try {
      const res = await apiFetch("/auth/resend-verification", {
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
