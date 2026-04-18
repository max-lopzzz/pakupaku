import { useState } from "react";
import "./Onboarding.css";
import { CONDITION_NOTES } from "../constants/conditionNotes";

import puppyWave    from "../assets/images/puppy_wave.png";
import puppyBlush   from "../assets/images/puppy_blush.png";
import puppyNervous from "../assets/images/puppy_nervous.png";
import puppyShock   from "../assets/images/puppy_shock.png";
import puppyCheer   from "../assets/images/puppy_cheer.png";
import puppyStrong  from "../assets/images/puppy_strong.png";
import puppySparkle from "../assets/images/puppy_sparkle.png";
import puppyProud   from "../assets/images/puppy_proud.png";

// All UI assets are served from /public — no webpack imports needed
const PUB         = process.env.PUBLIC_URL || "";
const SVG_HEART   = `${PUB}/heart.png`;

// ─── Types ────────────────────────────────────────────────

type Step =
  | "welcome" | "dietitian" | "biometrics" | "hormonal" | "hrt"
  | "bodyshape" | "measurements" | "activity" | "goal" | "pace"
  | "conditions" | "done";

interface FormState {
  usesCustom:      boolean;
  customKcal:      string;
  customProtein:   string;
  customFat:       string;
  customCarbs:     string;
  weightKg:        string;
  heightCm:        string;
  birthday:        string;   // ISO date string, e.g. "1998-03-12"
  hormonalProfile: string;
  hrtType:         string;
  hrtStartDate:    string;   // ISO date string, approximate is fine
  navyProfile:     string;
  waistCm:         string;
  neckCm:          string;
  hipCm:           string;
  activityLevel:   string;
  goal:            string;
  paceKgPerWeek:   number;
  conditions:      string[];
}

function calcAge(birthday: string): number {
  if (!birthday) return 0;
  const today = new Date();
  const dob   = new Date(birthday);
  let age     = today.getFullYear() - dob.getFullYear();
  const m     = today.getMonth() - dob.getMonth();
  if (m < 0 || (m === 0 && today.getDate() < dob.getDate())) age--;
  return age;
}

function calcHrtMonths(startDate: string): number {
  if (!startDate) return 0;
  const today = new Date();
  const start = new Date(startDate);
  return Math.max(0, Math.round(
    (today.getFullYear() - start.getFullYear()) * 12 +
    (today.getMonth()   - start.getMonth())
  ));
}

type Errors = Partial<Record<
  keyof FormState | "submit" | "hormonalProfile" | "navyProfile" |
  "activityLevel" | "hrtType" | "hrtMonths" | "age",
  string
>>;

interface OnboardingProps {
  onComplete: (data?: unknown) => void;
}

// ─── Constants ────────────────────────────────────────────

const STEPS: Step[] = [
  "welcome", "dietitian", "biometrics", "hormonal", "hrt",
  "bodyshape", "measurements", "activity", "goal", "pace",
  "conditions", "done",
];

const CONDITIONS_LIST = [
  { key: "hypothyroidism_untreated", label: "Hypothyroidism (untreated)" },
  { key: "hypothyroidism_treated",   label: "Hypothyroidism (treated)" },
  { key: "hyperthyroidism_untreated",label: "Hyperthyroidism (untreated)" },
  { key: "hyperthyroidism_treated",  label: "Hyperthyroidism (treated)" },
  { key: "hiv_wasting",              label: "HIV/AIDS with wasting" },
  { key: "cancer_active",            label: "Cancer (active)" },
  { key: "pcos",                     label: "PCOS" },
  { key: "cushings",                 label: "Cushing's Syndrome" },
  { key: "diabetes_t1",              label: "Type 1 Diabetes" },
  { key: "eating_disorder_history",  label: "Eating disorder history" },
  { key: "fibromyalgia",             label: "Fibromyalgia" },
];

const STEP_MASCOT: Record<Step, { img: string; mood: string }> = {
  welcome:      { img: puppyWave,    mood: "wave" },
  dietitian:    { img: puppyBlush,   mood: "blush" },
  biometrics:   { img: puppyShock,   mood: "think" },
  hormonal:     { img: puppySparkle, mood: "sparkle" },
  hrt:          { img: puppyNervous, mood: "nervous" },
  bodyshape:    { img: puppyShock,   mood: "think" },
  measurements: { img: puppyStrong,  mood: "strong" },
  activity:     { img: puppyCheer,   mood: "cheer" },
  goal:         { img: puppySparkle, mood: "sparkle" },
  pace:         { img: puppyNervous, mood: "nervous" },
  conditions:   { img: puppyBlush,   mood: "blush" },
  done:         { img: puppyProud,   mood: "proud" },
};

// ─── Main component ───────────────────────────────────────

export default function Onboarding({ onComplete }: OnboardingProps) {
  const [step, setStep]       = useState<Step>("welcome");
  const [form, setForm]       = useState<FormState>({
    usesCustom: false,
    customKcal: "", customProtein: "", customFat: "", customCarbs: "",
    weightKg: "", heightCm: "", birthday: "",
    hormonalProfile: "",
    hrtType: "", hrtStartDate: "",
    navyProfile: "",
    waistCm: "", neckCm: "", hipCm: "",
    activityLevel: "",
    goal: "",
    paceKgPerWeek: 0.5,
    conditions: [],
  });
  const [errors, setErrors]   = useState<Errors>({});
  const [loading, setLoading] = useState(false);

  const set = (key: keyof FormState, val: string | number | boolean | string[]) =>
    setForm(f => ({ ...f, [key]: val }));

  const toggleCondition = (key: string) => {
    setForm(f => ({
      ...f,
      conditions: f.conditions.includes(key)
        ? f.conditions.filter(k => k !== key)
        : [...f.conditions, key],
    }));
  };

  const validate = (): boolean => {
    const e: Errors = {};
    if (step === "biometrics") {
      if (!form.weightKg || isNaN(Number(form.weightKg))) e.weightKg = "Enter a valid weight";
      if (!form.heightCm || isNaN(Number(form.heightCm))) e.heightCm = "Enter a valid height";
      if (!form.birthday) {
        e.age = "Enter your date of birth";
      } else {
        const age = calcAge(form.birthday);
        if (age < 10 || age > 120) e.age = "Enter a valid date of birth";
      }
    }
    if (step === "hormonal" && !form.hormonalProfile) e.hormonalProfile = "Please choose one";
    if (step === "hrt") {
      if (!form.hrtType)       e.hrtType      = "Please choose one";
      if (!form.hrtStartDate)  e.hrtMonths    = "Enter your HRT start date";
      else if (new Date(form.hrtStartDate) > new Date()) e.hrtMonths = "Start date can't be in the future";
    }
    if (step === "bodyshape"    && !form.navyProfile)    e.navyProfile    = "Please choose one";
    if (step === "measurements") {
      if (!form.waistCm || isNaN(Number(form.waistCm))) e.waistCm = "Enter waist measurement";
      if (!form.neckCm  || isNaN(Number(form.neckCm)))  e.neckCm  = "Enter neck measurement";
      if (["female","average","blend"].includes(form.navyProfile) &&
          (!form.hipCm || isNaN(Number(form.hipCm))))   e.hipCm   = "Enter hip measurement";
    }
    if (step === "activity" && !form.activityLevel) e.activityLevel = "Please choose one";
    if (step === "goal"     && !form.goal)           e.goal          = "Please choose one";
    if (step === "dietitian" && form.usesCustom) {
      if (!form.customKcal    || isNaN(Number(form.customKcal)))    e.customKcal    = "Enter calories";
      if (!form.customProtein || isNaN(Number(form.customProtein))) e.customProtein = "Enter protein";
      if (!form.customFat     || isNaN(Number(form.customFat)))     e.customFat     = "Enter fat";
      if (!form.customCarbs   || isNaN(Number(form.customCarbs)))   e.customCarbs   = "Enter carbs";
    }
    setErrors(e);
    return Object.keys(e).length === 0;
  };

  const nextStep = () => {
    if (!validate()) return;
    if (step === "welcome")   { setStep("dietitian");   return; }
    if (step === "dietitian") {
      if (form.usesCustom) { submitCustom(); return; }
      setStep("biometrics"); return;
    }
    if (step === "hormonal") {
      if (form.hormonalProfile === "hrt") { setStep("hrt"); return; }
      setStep("bodyshape"); return;
    }
    if (step === "hrt")          { setStep("bodyshape");  return; }
    if (step === "measurements") { setStep("activity");   return; }
    if (step === "activity")     { setStep("goal");       return; }
    if (step === "goal") {
      if (form.goal === "maintain") { setStep("conditions"); return; }
      setStep("pace"); return;
    }
    if (step === "pace")       { setStep("conditions"); return; }
    if (step === "conditions") { submitCalculated();    return; }
    const idx  = STEPS.indexOf(step);
    const next = STEPS[idx + 1];
    if (next) setStep(next);
  };

  const prevStep = () => {
    if (step === "welcome") return;
    if (step === "biometrics" && !form.usesCustom) { setStep("dietitian");  return; }
    if (step === "hrt")                            { setStep("hormonal");   return; }
    if (step === "bodyshape") {
      if (form.hormonalProfile === "hrt") { setStep("hrt"); return; }
      setStep("hormonal"); return;
    }
    if (step === "conditions" && form.goal === "maintain") { setStep("goal"); return; }
    if (step === "conditions") { setStep("pace"); return; }
    const idx = STEPS.indexOf(step);
    if (idx > 0) setStep(STEPS[idx - 1]);
  };

  const submitCustom = async () => {
    if (!validate()) return;
    setLoading(true);
    setErrors({});
    try {
      const token = localStorage.getItem("token");
      const res = await fetch("/users/me/onboarding/custom", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          custom_kcal:    parseFloat(form.customKcal),
          custom_protein: parseFloat(form.customProtein),
          custom_fat:     parseFloat(form.customFat),
          custom_carbs:   parseFloat(form.customCarbs),
        }),
      });
      
      if (!res.ok) {
        const errorData = await res.json();
        console.error("Custom goals error:", errorData);
        setErrors({ submit: errorData.detail || "Failed to save custom goals." });
        return;
      }
      
      setStep("done");
    } catch (error) {
      console.error("Custom goals submission error:", error);
      setErrors({ submit: "Something went wrong. Please try again." });
    } finally {
      setLoading(false);
    }
  };

  const submitCalculated = async () => {
    setLoading(true);
    setErrors({});
    try {
      const token = localStorage.getItem("token");
      const res = await fetch("/users/me/onboarding/calculate", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          weight_kg:            parseFloat(form.weightKg),
          height_cm:            parseFloat(form.heightCm),
          age:                  calcAge(form.birthday),
          birthday:             form.birthday || undefined,
          hormonal_profile:     form.hormonalProfile,
          hrt_type:             form.hrtType       || null,
          hrt_months:           form.hrtStartDate ? calcHrtMonths(form.hrtStartDate) : null,
          navy_profile:         form.navyProfile,
          waist_cm:             parseFloat(form.waistCm),
          neck_cm:              parseFloat(form.neckCm),
          hip_cm:               form.hipCm ? parseFloat(form.hipCm) : null,
          activity_level:       form.activityLevel,
          goal:                 form.goal,
          pace_kg_per_week:     form.paceKgPerWeek,
          metabolic_conditions: form.conditions,
        }),
      });
      
      if (!res.ok) {
        const errorData = await res.json();
        console.error("Calculation error:", errorData);
        setErrors({ submit: errorData.detail || "Failed to calculate goals. Please check your inputs." });
        return;
      }
      
      const data = await res.json();
      setStep("done");
      if (onComplete) onComplete(data);
    } catch (error) {
      console.error("Submission error:", error);
      setErrors({ submit: "Something went wrong. Please try again." });
    } finally {
      setLoading(false);
    }
  };

  const mascot   = STEP_MASCOT[step];
  const progress = Math.round((STEPS.indexOf(step) / (STEPS.length - 1)) * 100);

  return (
    <div
      className="onboarding-root"
      style={{ backgroundImage: `url(${PUB}/polka_dots.png)` }}
    >
      <div className="onboarding-card">
        <div className="onboarding-mascot-wrap">
          <img
            src={mascot.img} alt=""
            className={`onboarding-mascot mascot-${mascot.mood}`}
            key={step}
          />
        </div>
        {step !== "welcome" && step !== "done" && (
          <div className="onboarding-progress-bar" aria-hidden="true">
            <div className="onboarding-progress-fill" style={{ width: `${progress}%` }} />
          </div>
        )}
        <div className="onboarding-body">
          {step === "welcome"      && <StepWelcome onNext={nextStep} />}
          {step === "dietitian"    && <StepDietitian    form={form} set={set} errors={errors} onNext={nextStep} onBack={prevStep} />}
          {step === "biometrics"   && <StepBiometrics   form={form} set={set} errors={errors} onNext={nextStep} onBack={prevStep} />}
          {step === "hormonal"     && <StepHormonal     form={form} set={set} errors={errors} onNext={nextStep} onBack={prevStep} />}
          {step === "hrt"          && <StepHRT          form={form} set={set} errors={errors} onNext={nextStep} onBack={prevStep} />}
          {step === "bodyshape"    && <StepBodyShape    form={form} set={set} errors={errors} onNext={nextStep} onBack={prevStep} />}
          {step === "measurements" && <StepMeasurements form={form} set={set} errors={errors} onNext={nextStep} onBack={prevStep} />}
          {step === "activity"     && <StepActivity     form={form} set={set} errors={errors} onNext={nextStep} onBack={prevStep} />}
          {step === "goal"         && <StepGoal         form={form} set={set} errors={errors} onNext={nextStep} onBack={prevStep} />}
          {step === "pace"         && <StepPace         form={form} set={set} onNext={nextStep} onBack={prevStep} />}
          {step === "conditions"   && (
            <StepConditions
              form={form} toggleCondition={toggleCondition}
              onNext={nextStep} onBack={prevStep}
              loading={loading} errors={errors}
            />
          )}
          {step === "done" && <StepDone onComplete={onComplete} />}
        </div>
      </div>
    </div>
  );
}

// ─── Shared prop types ────────────────────────────────────

type SetFn = (key: keyof FormState, val: string | number | boolean | string[]) => void;

interface StepProps {
  form:   FormState;
  set:    SetFn;
  errors: Errors;
  onNext: () => void;
  onBack: () => void;
}

// ─── Step components ──────────────────────────────────────

function StepWelcome({ onNext }: { onNext: () => void }) {
  return (
    <div className="step-content">
      <StepTitle h1>welcome to <span className="brand">pakupaku!</span></StepTitle>
      <p className="step-desc">
        let's set up your nutrition profile. it only takes a few minutes
        and everything stays private to you. ✨
      </p>
      <PrimaryBtn onClick={onNext}>let's go!</PrimaryBtn>
    </div>
  );
}

function StepDietitian({ form, set, errors, onNext, onBack }: StepProps) {
  return (
    <div className="step-content">
      <StepTitle>do you have a dietitian?</StepTitle>
      <p className="step-desc">
        if a professional has already given you calorie and macro goals,
        you can enter them directly and skip the calculator.
      </p>
      <div className="choice-group">
        <HeartBtn selected={!form.usesCustom} onClick={() => set("usesCustom", false)}>
          calculate for me
        </HeartBtn>
        <HeartBtn selected={form.usesCustom} onClick={() => set("usesCustom", true)}>
          i have my own goals
        </HeartBtn>
      </div>
      {form.usesCustom && (
        <div className="field-group">
          <Field label="daily calories (kcal)" error={errors.customKcal}>
            <input type="number" placeholder="e.g. 1800" value={form.customKcal}
              onChange={e => set("customKcal", e.target.value)} />
          </Field>
          <Field label="protein (g)" error={errors.customProtein}>
            <input type="number" placeholder="e.g. 120" value={form.customProtein}
              onChange={e => set("customProtein", e.target.value)} />
          </Field>
          <div className="field-row">
            <Field label="fat (g)" error={errors.customFat}>
              <input type="number" placeholder="e.g. 60" value={form.customFat}
                onChange={e => set("customFat", e.target.value)} />
            </Field>
            <Field label="carbs (g)" error={errors.customCarbs}>
              <input type="number" placeholder="e.g. 200" value={form.customCarbs}
                onChange={e => set("customCarbs", e.target.value)} />
            </Field>
          </div>
          <ErrorMsg msg={errors.submit} />
        </div>
      )}
      <NavButtons onBack={onBack} onNext={onNext}
        nextLabel={form.usesCustom ? "save my goals" : "next"} />
    </div>
  );
}

function StepBiometrics({ form, set, errors, onNext, onBack }: StepProps) {
  const age = form.birthday ? calcAge(form.birthday) : null;
  // Max date = today (can't be born in the future)
  const maxDate = new Date().toISOString().slice(0, 10);
  return (
    <div className="step-content">
      <StepTitle>tell us about yourself</StepTitle>
      <p className="step-desc">these help calculate your baseline calorie needs.</p>
      <div className="field-group">
        <div className="field-row">
          <Field label="weight (kg)" error={errors.weightKg}>
            <input type="number" placeholder="e.g. 65" value={form.weightKg}
              onChange={e => set("weightKg", e.target.value)} />
          </Field>
          <Field label="height (cm)" error={errors.heightCm}>
            <input type="number" placeholder="e.g. 168" value={form.heightCm}
              onChange={e => set("heightCm", e.target.value)} />
          </Field>
        </div>
        <Field label={age !== null ? `date of birth (age: ${age})` : "date of birth"} error={errors.age}>
          <input type="date" value={form.birthday} max={maxDate}
            onChange={e => set("birthday", e.target.value)} />
        </Field>
      </div>
      <NavButtons onBack={onBack} onNext={onNext} />
    </div>
  );
}

function StepHormonal({ form, set, errors, onNext, onBack }: StepProps) {
  const options = [
    { value: "male",    label: "male physiology",   sub: "cis male, or trans male (1+ yr on T)" },
    { value: "female",  label: "female physiology", sub: "cis female, or trans female (2+ yr on E)" },
    { value: "hrt",     label: "currently on HRT",  sub: "transition in progress — tell us more next" },
    { value: "average", label: "averaging both",    sub: "non-binary or unsure which fits" },
    { value: "katch",   label: "sex-neutral",       sub: "uses lean body mass — most inclusive" },
  ];
  return (
    <div className="step-content">
      <StepTitle>hormonal profile</StepTitle>
      <p className="step-desc">
        picks the most accurate BMR formula. separate from your gender identity.
      </p>
      <div className="radio-group">
        {options.map(o => (
          <HeartBtn key={o.value} selected={form.hormonalProfile === o.value}
            onClick={() => set("hormonalProfile", o.value)} wide>
            <span className="radio-label">{o.label}</span>
            <span className="radio-sub">{o.sub}</span>
          </HeartBtn>
        ))}
      </div>
      <ErrorMsg msg={errors.hormonalProfile} />
      <NavButtons onBack={onBack} onNext={onNext} />
    </div>
  );
}

function StepHRT({ form, set, errors, onNext, onBack }: StepProps) {
  const months = form.hrtStartDate ? calcHrtMonths(form.hrtStartDate) : null;
  const maxDate = new Date().toISOString().slice(0, 10);
  return (
    <div className="step-content">
      <StepTitle>HRT details</StepTitle>
      <p className="step-desc">
        helps us blend the formula gradually over your transition timeline.
      </p>
      <div className="choice-group">
        <HeartBtn selected={form.hrtType === "estrogen"}
          onClick={() => set("hrtType", "estrogen")}>estrogen</HeartBtn>
        <HeartBtn selected={form.hrtType === "testosterone"}
          onClick={() => set("hrtType", "testosterone")}>testosterone</HeartBtn>
      </div>
      <ErrorMsg msg={errors.hrtType} />
      <Field
        label={months !== null ? `HRT start date (${months} month${months !== 1 ? "s" : ""} ago)` : "HRT start date"}
        error={errors.hrtMonths}
      >
        <input type="date" value={form.hrtStartDate} max={maxDate}
          onChange={e => set("hrtStartDate", e.target.value)} />
      </Field>
      <p className="step-desc" style={{ fontSize: "0.85rem", marginTop: "0.25rem" }}>
        an approximate date is fine.
      </p>
      <NavButtons onBack={onBack} onNext={onNext} />
    </div>
  );
}

function StepBodyShape({ form, set, errors, onNext, onBack }: StepProps) {
  const options = [
    { value: "male",    label: "mainly around the waist",     sub: "android / apple — no hip needed" },
    { value: "female",  label: "hips and thighs too",         sub: "gynoid / pear — hip measurement needed" },
    { value: "blend",   label: "blend based on HRT timeline", sub: "uses HRT months to interpolate" },
    { value: "average", label: "not sure — enter both",       sub: "hip needed, we'll average the formulas" },
  ];
  return (
    <div className="step-content">
      <StepTitle>body fat formula</StepTitle>
      <p className="step-desc">where does your body mainly store fat right now?</p>
      <div className="radio-group">
        {options.map(o => (
          <HeartBtn key={o.value} selected={form.navyProfile === o.value}
            onClick={() => set("navyProfile", o.value)} wide>
            <span className="radio-label">{o.label}</span>
            <span className="radio-sub">{o.sub}</span>
          </HeartBtn>
        ))}
      </div>
      <ErrorMsg msg={errors.navyProfile} />
      <NavButtons onBack={onBack} onNext={onNext} />
    </div>
  );
}

function StepMeasurements({ form, set, errors, onNext, onBack }: StepProps) {
  const needsHip = ["female", "average", "blend"].includes(form.navyProfile);
  return (
    <div className="step-content">
      <StepTitle>body measurements</StepTitle>
      <p className="step-desc">measure at the widest point, in centimeters.</p>
      <div className="field-group">
        <div className="field-row">
          <Field label="waist (cm)" error={errors.waistCm}>
            <input type="number" placeholder="e.g. 80" value={form.waistCm}
              onChange={e => set("waistCm", e.target.value)} />
          </Field>
          <Field label="neck (cm)" error={errors.neckCm}>
            <input type="number" placeholder="e.g. 34" value={form.neckCm}
              onChange={e => set("neckCm", e.target.value)} />
          </Field>
        </div>
        {needsHip && (
          <Field label="hips (cm)" error={errors.hipCm}>
            <input type="number" placeholder="e.g. 95" value={form.hipCm}
              onChange={e => set("hipCm", e.target.value)} />
          </Field>
        )}
      </div>
      <NavButtons onBack={onBack} onNext={onNext} />
    </div>
  );
}

function StepActivity({ form, set, errors, onNext, onBack }: StepProps) {
  const options = [
    { value: "sedentary",   label: "sedentary",        sub: "desk job, little or no exercise" },
    { value: "light",       label: "lightly active",   sub: "1–3 days/week" },
    { value: "moderate",    label: "moderately active", sub: "3–5 days/week" },
    { value: "very_active", label: "very active",      sub: "6–7 days/week" },
    { value: "extreme",     label: "extremely active", sub: "physical job + daily training" },
  ];
  return (
    <div className="step-content">
      <StepTitle>activity level</StepTitle>
      <p className="step-desc">how active are you on a typical week?</p>
      <div className="radio-group">
        {options.map(o => (
          <HeartBtn key={o.value} selected={form.activityLevel === o.value}
            onClick={() => set("activityLevel", o.value)} wide>
            <span className="radio-label">{o.label}</span>
            <span className="radio-sub">{o.sub}</span>
          </HeartBtn>
        ))}
      </div>
      <ErrorMsg msg={errors.activityLevel} />
      <NavButtons onBack={onBack} onNext={onNext} />
    </div>
  );
}

function StepGoal({ form, set, errors, onNext, onBack }: StepProps) {
  const options = [
    { value: "lose",     label: "lose weight",        sub: "caloric deficit" },
    { value: "maintain", label: "maintain",            sub: "stay where i am" },
    { value: "gain",     label: "gain / build muscle", sub: "caloric surplus" },
  ];
  return (
    <div className="step-content">
      <StepTitle>what's your goal?</StepTitle>
      <div className="radio-group">
        {options.map(o => (
          <HeartBtn key={o.value} selected={form.goal === o.value}
            onClick={() => set("goal", o.value)} wide>
            <span className="radio-label">{o.label}</span>
            <span className="radio-sub">{o.sub}</span>
          </HeartBtn>
        ))}
      </div>
      <ErrorMsg msg={errors.goal} />
      <NavButtons onBack={onBack} onNext={onNext} />
    </div>
  );
}

function StepPace({
  form, set, onNext, onBack,
}: { form: FormState; set: SetFn; onNext: () => void; onBack: () => void }) {
  const isLose  = form.goal === "lose";
  const presets = isLose
    ? [{ v: 0.25, l: "slow",      s: "0.25 kg/week" },
       { v: 0.5,  l: "moderate",  s: "0.50 kg/week" },
       { v: 0.75, l: "fast",      s: "0.75 kg/week" },
       { v: 1.0,  l: "max safe",  s: "1.00 kg/week" }]
    : [{ v: 0.10, l: "lean bulk",  s: "0.10 kg/week" },
       { v: 0.20, l: "moderate",   s: "0.20 kg/week" },
       { v: 0.35, l: "aggressive", s: "0.35 kg/week" }];
  return (
    <div className="step-content">
      <StepTitle>how fast?</StepTitle>
      <p className="step-desc">
        {isLose ? "slower = more sustainable and less muscle loss."
                : "slower = less fat gain alongside the muscle."}
      </p>
      <div className="pace-presets">
        {presets.map(p => (
          <HeartBtn key={p.v} selected={form.paceKgPerWeek === p.v}
            onClick={() => set("paceKgPerWeek", p.v)}>
            <span className="pace-label">{p.l}</span>
            <span className="pace-sub">{p.s}</span>
          </HeartBtn>
        ))}
      </div>
      <div className="pace-slider-wrap">
        <label className="slider-label">
          custom: {form.paceKgPerWeek.toFixed(2)} kg/week
        </label>
        <input type="range"
          min={isLose ? 0.1 : 0.05} max={isLose ? 1.0 : 0.5}
          step="0.05" value={form.paceKgPerWeek}
          onChange={e => set("paceKgPerWeek", parseFloat(e.target.value))} />
      </div>
      <NavButtons onBack={onBack} onNext={onNext} />
    </div>
  );
}

function StepConditions({
  form, toggleCondition, onNext, onBack, loading, errors,
}: {
  form: FormState;
  toggleCondition: (key: string) => void;
  onNext: () => void;
  onBack: () => void;
  loading: boolean;
  errors: Errors;
}) {
  return (
    <div className="step-content">
      <StepTitle>any health conditions?</StepTitle>
      <p className="step-desc">
        select all that apply, or skip if none apply to you.
      </p>
      <div className="conditions-list">
        {CONDITIONS_LIST.map(c => {
          const selected = form.conditions.includes(c.key);
          const note = CONDITION_NOTES[c.key];
          return (
            <div key={c.key} className="condition-item">
              <HeartBtn selected={selected} onClick={() => toggleCondition(c.key)} pill>
                {c.label}
              </HeartBtn>
              {selected && note && (
                <p className="condition-inline-note">{note.onboardingNote}</p>
              )}
            </div>
          );
        })}
      </div>
      <ErrorMsg msg={errors.submit} />
      <NavButtons onBack={onBack} onNext={onNext}
        nextLabel={loading ? "calculating..." : "calculate my goals!"}
        disabled={loading} />
    </div>
  );
}

function StepDone({ onComplete }: { onComplete: (data?: unknown) => void }) {
  return (
    <div className="step-content step-done">
      <img src={SVG_HEART} className="done-heart" alt="" aria-hidden="true" />
      <StepTitle>you're all set!</StepTitle>
      <p className="step-desc">your nutrition profile is ready. let's start tracking!</p>
      <PrimaryBtn onClick={() => onComplete()}>go to my dashboard</PrimaryBtn>
    </div>
  );
}

// ─── Shared UI components ─────────────────────────────────

function StepTitle({ children, h1 }: { children: React.ReactNode; h1?: boolean }) {
  const Tag = h1 ? "h1" : "h2";
  return (
    <div className="step-title-wrap">
      <Tag className="step-title">{children}</Tag>
    </div>
  );
}
function PrimaryBtn({
  children, onClick, disabled,
}: { children: React.ReactNode; onClick: () => void; disabled?: boolean }) {
  return (
    <button
      className="btn-primary"
      onClick={onClick}
      disabled={disabled}
    >
      <span className="btn-text">{children}</span>
    </button>
  );
}

function HeartBtn({
  children, selected, onClick, wide, pill,
}: {
  children: React.ReactNode;
  selected: boolean;
  onClick: () => void;
  wide?: boolean;
  pill?: boolean;
}) {
  return (
    <button
      className={`heart-btn ${selected ? "selected" : ""} ${wide ? "wide" : ""} ${pill ? "pill" : ""}`}
      onClick={onClick}
    >
      <span className="heart-btn-content">{children}</span>
    </button>
  );
}

function ErrorMsg({ msg }: { msg?: string }) {
  if (!msg) return null;
  return (
    <div className="error-msg-wrap">
      <p className="error-msg">{msg}</p>
    </div>
  );
}

function Field({
  label, error, children,
}: { label: string; error?: string; children: React.ReactNode }) {
  return (
    <div className="field">
      <label className="field-label">{label}</label>
      <div className="field-input-wrap">
        {children}
      </div>
      {error && <span className="field-error">{error}</span>}
    </div>
  );
}

function NavButtons({
  onBack, onNext, nextLabel = "next", disabled = false,
}: { onBack: () => void; onNext: () => void; nextLabel?: string; disabled?: boolean }) {
  return (
    <div className="nav-buttons">
      <button className="btn-back" onClick={onBack}>back</button>
      <PrimaryBtn onClick={onNext} disabled={disabled}>{nextLabel}</PrimaryBtn>
    </div>
  );
}