import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import MealPlanner from "./MealPlanner";

const planResponse = {
  id: "11111111-1111-1111-1111-111111111111",
  days: 1,
  meals_per_day: 3,
  created_at: "2026-09-10T00:00:00Z",
  targets: { kcal: 2000, protein_g: 120, fat_g: 65, carbs_g: 220 },
  plan_days: [
    {
      day_index: 0,
      logged_at: null,
      structurally_unfilled_slots: [],
      totals: { calories: 1950, protein_g: 118, fat_g: 62, carbs_g: 210, fiber_g: 30 },
      entries: [
        { id: "e1", slot: "breakfast", servings: 1.1, unfilled: false,
          recipe: { id: "r1", name: "Overnight Oats", image_url: null, servings: 1,
                    meal_type: "breakfast", total_calories: 450, total_protein_g: 20,
                    total_fat_g: 10, total_carbs_g: 70, total_fiber_g: 8 },
          calories: 495, protein_g: 22, fat_g: 11, carbs_g: 77, fiber_g: 9 },
        { id: "e2", slot: "lunch", servings: 1, unfilled: false,
          recipe: { id: "r2", name: "Chickpea Salad", image_url: null, servings: 1,
                    meal_type: "lunch", total_calories: 650, total_protein_g: 40,
                    total_fat_g: 25, total_carbs_g: 60, total_fiber_g: 12 },
          calories: 650, protein_g: 40, fat_g: 25, carbs_g: 60, fiber_g: 12 },
        { id: "e3", slot: "dinner", servings: 1.2, unfilled: false,
          recipe: { id: "r3", name: "Lentil Curry", image_url: null, servings: 1,
                    meal_type: "dinner", total_calories: 700, total_protein_g: 45,
                    total_fat_g: 22, total_carbs_g: 78, total_fiber_g: 14 },
          calories: 805, protein_g: 56, fat_g: 26, carbs_g: 73, fiber_g: 9 },
      ],
    },
  ],
};

beforeEach(() => {
  localStorage.setItem("token", "t");
  global.fetch = jest.fn((url: RequestInfo | URL, init?: RequestInit) => {
    const u = String(url);
    if (u.endsWith("/meal-plan") && (!init || !init.method || init.method === "GET")) {
      return Promise.resolve({ ok: true, json: async () => null } as Response);
    }
    if (u.endsWith("/meal-plan/generate")) {
      return Promise.resolve({ ok: true, json: async () => planResponse } as Response);
    }
    return Promise.reject(new Error("unexpected " + u));
  }) as jest.Mock;
});
afterEach(() => { jest.restoreAllMocks(); localStorage.clear(); });

test("shows the generate form, then renders the plan with day totals", async () => {
  render(<MealPlanner onBack={() => {}} userProfile={{ diet_tags: [], safe_mode: false }} />);
  await waitFor(() => expect(screen.getByText("Generate plan")).toBeInTheDocument());

  fireEvent.click(screen.getByText("Generate plan"));

  await waitFor(() => expect(screen.getByText("Overnight Oats")).toBeInTheDocument());
  expect(screen.getByText("Chickpea Salad")).toBeInTheDocument();
  expect(screen.getByText("Lentil Curry")).toBeInTheDocument();
  // per-day totals vs target visible (calories number rendered somewhere)
  expect(screen.getByText(/1950/)).toBeInTheDocument();
});

test("pre-checks diet tags from the user profile", async () => {
  render(<MealPlanner onBack={() => {}} userProfile={{ diet_tags: ["vegan"], safe_mode: false }} />);
  await waitFor(() => expect(screen.getByText("Generate plan")).toBeInTheDocument());
  const vegan = screen.getByLabelText("vegan") as HTMLInputElement;
  expect(vegan.checked).toBe(true);
});

test("generate error is shown inline", async () => {
  (global.fetch as jest.Mock).mockImplementation((url: RequestInfo | URL) => {
    const u = String(url);
    if (u.endsWith("/meal-plan/generate")) {
      return Promise.resolve({ ok: false, json: async () => ({ detail: "Finish onboarding to set your calorie target before planning meals." }) } as Response);
    }
    return Promise.resolve({ ok: true, json: async () => null } as Response);
  });
  render(<MealPlanner onBack={() => {}} userProfile={{ diet_tags: [], safe_mode: false }} />);
  await waitFor(() => expect(screen.getByText("Generate plan")).toBeInTheDocument());
  fireEvent.click(screen.getByText("Generate plan"));
  await waitFor(() => expect(screen.getByText(/Finish onboarding/)).toBeInTheDocument());
});
