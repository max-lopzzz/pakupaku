// pakupaku-frontend/src/constants/conditionNotes.ts

export interface ConditionNote {
  label:          string;
  onboardingNote: string;   // shown inline when pill is selected in Onboarding
  dashboardNotes: string[]; // bullet points on the dashboard Health Notes card
  edWarning?:     boolean;  // if true, show ED warning in MealPlanner for extreme diets
}

export const CONDITION_NOTES: Record<string, ConditionNote> = {
  hypothyroidism_untreated: {
    label: "Hypothyroidism (untreated)",
    onboardingNote:
      "Thyroid function can significantly lower your resting metabolism. " +
      "Iodine and selenium support thyroid health — your goals will reflect this.",
    dashboardNotes: [
      "Prioritise iodine-rich foods: seafood, dairy, and eggs.",
      "Include selenium sources: Brazil nuts (1–2/day), tuna, and sunflower seeds.",
      "Avoid excessive raw cruciferous vegetables (broccoli, kale, cauliflower) — cooking deactivates goitrogens.",
      "Fibre-rich foods help with the digestive slowdown common in hypothyroidism.",
      "Consult your endocrinologist before making major dietary changes.",
    ],
  },
  hypothyroidism_treated: {
    label: "Hypothyroidism (treated)",
    onboardingNote:
      "With medication, your metabolism is likely closer to normal. " +
      "A few timing and nutrient considerations still apply.",
    dashboardNotes: [
      "Take thyroid medication at least 30–60 min before calcium or iron-rich meals.",
      "Iodine-containing foods are generally fine in normal amounts.",
      "Selenium-rich foods (Brazil nuts, tuna) remain beneficial.",
      "Maintain consistent meal timing to support stable hormone levels.",
    ],
  },
  hyperthyroidism_untreated: {
    label: "Hyperthyroidism (untreated)",
    onboardingNote:
      "Your metabolism is running faster than usual, raising calorie needs " +
      "and increasing bone-loss risk. Your goals account for this.",
    dashboardNotes: [
      "Limit iodine-rich foods: seaweed, kelp, and nori, as iodine can worsen hyperthyroidism.",
      "Increase calcium and vitamin D to protect bones (dairy, fortified plant milks, leafy greens).",
      "Higher calorie needs until thyroid levels are controlled — do not restrict aggressively.",
      "Avoid excess caffeine, which can worsen heart-rate symptoms.",
      "Work closely with your endocrinologist on timing of treatment and diet.",
    ],
  },
  hyperthyroidism_treated: {
    label: "Hyperthyroidism (treated)",
    onboardingNote:
      "Medication brings metabolism closer to normal. Bone density remains " +
      "a priority even after levels stabilise.",
    dashboardNotes: [
      "Ensure adequate calcium (1000–1200 mg/day) and vitamin D for bone health.",
      "Balanced macronutrients — no specific restrictions once levels are controlled.",
      "Moderate caffeine intake.",
      "Regular check-ins with your endocrinologist to monitor levels.",
    ],
  },
  hiv_wasting: {
    label: "HIV/AIDS with wasting",
    onboardingNote:
      "Higher protein and calorie needs are built into your targets to " +
      "support immune function and muscle preservation.",
    dashboardNotes: [
      "Aim for 1.5–2 g of protein per kg of body weight daily.",
      "Choose calorie-dense, nutrient-rich foods: nuts, nut butters, avocado, oily fish.",
      "Food safety is critical — avoid raw or undercooked meat, fish, and eggs.",
      "Frequent smaller meals can help if appetite is reduced.",
      "A dietitian specialising in HIV care can provide personalised guidance.",
    ],
  },
  cancer_active: {
    label: "Cancer (active)",
    onboardingNote:
      "Nutritional needs vary by cancer type and treatment phase. " +
      "Your targets prioritise protein and nutrient density.",
    dashboardNotes: [
      "Prioritise protein to preserve muscle mass during treatment.",
      "Choose easy-to-digest foods if experiencing nausea or mouth sores.",
      "Experiment with temperature and texture — cold or room-temperature foods are often better tolerated.",
      "Stay well hydrated, especially during chemotherapy or radiation.",
      "An oncology dietitian can tailor recommendations to your specific treatment.",
    ],
  },
  pcos: {
    label: "PCOS",
    onboardingNote:
      "A low-GI, anti-inflammatory diet can improve insulin sensitivity " +
      "and help manage PCOS symptoms alongside your calorie targets.",
    dashboardNotes: [
      "Favour low-GI carbohydrates: oats, legumes, sweet potato, and whole grains.",
      "Increase omega-3 sources: oily fish (salmon, sardines), walnuts, and flaxseed.",
      "Limit refined sugars and ultra-processed foods.",
      "Inositol-rich foods (citrus, beans, whole grains) may support hormonal balance.",
      "Regular, evenly spaced meals help stabilise blood sugar throughout the day.",
    ],
  },
  cushings: {
    label: "Cushing's Syndrome",
    onboardingNote:
      "Cortisol excess affects fat distribution, blood pressure, and bone " +
      "density. Your meal plan reflects lower-sodium, bone-supportive guidance.",
    dashboardNotes: [
      "Limit sodium: avoid processed foods, soy sauce, canned soups, and pickles.",
      "Reduce simple carbohydrates to support blood sugar management.",
      "Prioritise potassium-rich foods: banana, spinach, avocado, and sweet potato.",
      "Ensure adequate calcium and vitamin D for bone protection.",
      "Avoid alcohol, which worsens cortisol-related metabolic effects.",
    ],
  },
  diabetes_t1: {
    label: "Type 1 Diabetes",
    onboardingNote:
      "Consistent carbohydrate intake and timing work alongside insulin " +
      "management. Your targets support steady blood sugar, not elimination of carbs.",
    dashboardNotes: [
      "Distribute carbohydrates consistently across meals rather than skipping them.",
      "Favour low-GI carbohydrate sources to reduce blood glucose spikes.",
      "Pair carbohydrates with protein or fat to blunt the glucose response.",
      "Keep fast-acting glucose (juice, glucose tablets) accessible at all times.",
      "Your diabetes care team can fine-tune your targets and insulin-to-carb ratio.",
    ],
  },
  eating_disorder_history: {
    label: "Eating disorder history",
    onboardingNote:
      "All foods fit — regular, balanced eating supports both physical and " +
      "mental wellbeing. Calorie counts are a guide, not a rule.",
    dashboardNotes: [
      "Aim for regular, structured meal times to build a consistent relationship with food.",
      "Include all food groups — no foods are forbidden here.",
      "Focus on how food makes you feel rather than numbers alone.",
      "If difficult thoughts arise around eating, support is available: " +
        "Beat (UK) beateatingdisorders.org.uk · NEDA (US) nationaleatingdisorders.org · " +
        "ANAD (US) anad.org",
    ],
    edWarning: true,
  },
  fibromyalgia: {
    label: "Fibromyalgia",
    onboardingNote:
      "An anti-inflammatory diet may help manage pain and fatigue. " +
      "Your targets account for potentially reduced activity tolerance.",
    dashboardNotes: [
      "Increase omega-3 sources: oily fish (salmon, mackerel), chia seeds, and flaxseed.",
      "Choose antioxidant-rich foods: colourful vegetables, berries, and green tea.",
      "Magnesium-rich foods may ease muscle tension: pumpkin seeds, dark chocolate, spinach, and almonds.",
      "Ensure adequate vitamin D — consider discussing supplementation with your doctor.",
      "Limit processed foods, excess alcohol, and caffeine, which can worsen fatigue and disrupt sleep.",
      "Small, regular meals help sustain energy across the day.",
    ],
  },
};
