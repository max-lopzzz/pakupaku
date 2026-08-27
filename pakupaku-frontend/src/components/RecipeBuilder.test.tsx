import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import RecipeBuilder from "./RecipeBuilder";

const draft = {
  name: "Test Pancakes",
  servings: 4,
  image_url: null,
  source_url: "https://example.com/pancakes",
  instructions: "Mix ingredients.\nCook on a griddle.",
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
    return Promise.reject(new Error(`Unexpected fetch: ${u}`));
  }) as jest.Mock;
});

afterEach(() => {
  jest.restoreAllMocks();
  localStorage.clear();
});

test("importing a URL pre-fills the recipe form", async () => {
  render(<RecipeBuilder onBack={() => {}} userProfile={{ is_admin: false }} />);

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

test("is_shared checkbox only appears for admins", () => {
  const { rerender } = render(<RecipeBuilder onBack={() => {}} userProfile={{ is_admin: false }} />);
  expect(screen.queryByText("Share in the shared recipe library")).not.toBeInTheDocument();

  rerender(<RecipeBuilder onBack={() => {}} userProfile={{ is_admin: true }} />);
  expect(screen.getByText("Share in the shared recipe library")).toBeInTheDocument();
});

test("importing a URL carries instructions into the form", async () => {
  render(<RecipeBuilder onBack={() => {}} userProfile={{ is_admin: false }} />);

  const urlInput = screen.getByPlaceholderText("https://example.com/some-recipe");
  fireEvent.change(urlInput, { target: { value: "https://example.com/pancakes" } });
  fireEvent.click(screen.getByText("Import"));

  await waitFor(() => {
    const textarea = screen.getByPlaceholderText(/One step per line/) as HTMLTextAreaElement;
    expect(textarea.value).toBe("Mix ingredients.\nCook on a griddle.");
  });
});
