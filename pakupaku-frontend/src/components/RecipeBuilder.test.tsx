import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import RecipeBuilder from "./RecipeBuilder";

const draft = {
  name: "Test Pancakes",
  servings: 4,
  image_url: null,
  source_url: "https://example.com/pancakes",
  ingredients: [
    {
      raw_line: "2 cups flour",
      quantity: 2,
      unit: "cup",
      food_name: "flour",
      best_match: {
        fdc_id: 123456,
        description: "Flour, wheat, all-purpose",
        brand: null,
        calories_per_100g: 364,
        protein_per_100g: 10,
        fat_per_100g: 1,
        carbs_per_100g: 76,
        fiber_per_100g: 2.7,
        portions_map: { cup: 125 },
      },
      alternates: [],
    },
  ],
};

const brandedGochujangSearch = {
  foods: [
    { fdcId: 1, description: "Gochujang", dataType: "Branded", brandOwner: "CJ", foodNutrients: [] },
    { fdcId: 2, description: "Gochujang", dataType: "Branded", brandOwner: "Sempio", foodNutrients: [] },
    { fdcId: 3, description: "Gochujang", dataType: "Branded", brandOwner: "Annie Chun's", foodNutrients: [] },
    { fdcId: 4, description: "Gochujang", dataType: "Branded", brandOwner: "Trader Joe's", foodNutrients: [] },
    { fdcId: 5, description: "Gochujang Hot Pepper Paste", dataType: "Branded", brandOwner: "Chung Jung One", foodNutrients: [] },
  ],
};

beforeEach(() => {
  localStorage.setItem("token", "test-token");
  global.fetch = jest.fn((url: RequestInfo | URL) => {
    const u = String(url);
    if (u === "/recipes") {
      return Promise.resolve({ ok: true, json: async () => [] } as Response);
    }
    if (u === "/recipes/import") {
      return Promise.resolve({ ok: true, json: async () => draft } as Response);
    }
    if (u.startsWith("/foods/search?query=gochujang")) {
      return Promise.resolve({ ok: true, json: async () => brandedGochujangSearch } as Response);
    }
    return Promise.reject(new Error(`Unexpected fetch: ${u}`));
  }) as jest.Mock;
});

afterEach(() => {
  jest.restoreAllMocks();
  localStorage.clear();
});

test("importing a URL pre-fills the recipe form", async () => {
  render(<RecipeBuilder onBack={() => {}} />);

  const urlInput = screen.getByPlaceholderText("https://example.com/some-recipe");
  fireEvent.change(urlInput, {
    target: { value: "https://example.com/pancakes" },
  });
  fireEvent.click(screen.getByText("Import"));

  await waitFor(() => {
    expect(screen.getByDisplayValue("Test Pancakes")).toBeInTheDocument();
  });
  expect(screen.getByDisplayValue("Flour, wheat, all-purpose")).toBeInTheDocument();
  expect(screen.getByDisplayValue("2")).toBeInTheDocument();
});

test("branded-only search results with the same description collapse to one suggestion", async () => {
  render(<RecipeBuilder onBack={() => {}} />);

  const searchInput = screen.getByPlaceholderText("Search food…");
  fireEvent.change(searchInput, { target: { value: "gochujang" } });

  await waitFor(
    () => {
      expect(screen.getAllByText("Gochujang").length).toBeGreaterThan(0);
    },
    { timeout: 2000 }
  );

  // 5 branded results came back, 4 sharing the exact description "Gochujang"
  // (from CJ/Sempio/Annie Chun's/Trader Joe's) and 1 with a distinct
  // description ("Gochujang Hot Pepper Paste") — expect the 4 duplicates
  // collapsed to 1, so 2 suggestion rows total, not 5.
  const items = document.querySelectorAll(".autocomplete-item");
  expect(items.length).toBe(2);
  expect(screen.getByText("Gochujang")).toBeInTheDocument();
  expect(screen.getByText("Gochujang Hot Pepper Paste")).toBeInTheDocument();
});
