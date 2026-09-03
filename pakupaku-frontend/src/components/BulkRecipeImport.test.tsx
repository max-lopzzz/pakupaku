import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import BulkRecipeImport from "./BulkRecipeImport";

const draftA = {
  name: "Chocolate Cake",
  servings: 8,
  image_url: null,
  source_url: "https://example.com/recipes/chocolate-cake/",
  instructions: "Mix. Bake.",
  ingredients: [
    {
      raw_line: "2 cups flour",
      quantity: 2,
      unit: "cup",
      food_name: "flour",
      best_match: {
        fdc_id: 111,
        description: "Flour, wheat, all-purpose",
        brand: null,
        calories_per_100g: 364,
        protein_per_100g: 10,
        fat_per_100g: 1,
        carbs_per_100g: 76,
        fiber_per_100g: 2.7,
        portions_map: {},
      },
      alternates: [],
    },
  ],
};

const draftB = {
  name: "Banana Bread",
  servings: 4,
  image_url: null,
  source_url: "https://example.com/recipes/banana-bread/",
  instructions: null,
  ingredients: [
    {
      raw_line: "3 bananas",
      quantity: 3,
      unit: "large",
      food_name: "bananas",
      best_match: null,
      alternates: [],
    },
  ],
};

beforeEach(() => {
  localStorage.setItem("token", "test-token");
  global.fetch = jest.fn((url: RequestInfo | URL, opts?: RequestInit) => {
    const u = String(url);
    if (u === "/recipes/bulk-import/discover") {
      return Promise.resolve({
        ok: true,
        json: async () => ({
          urls: [
            "https://example.com/recipes/chocolate-cake/",
            "https://example.com/recipes/banana-bread/",
          ],
        }),
      } as Response);
    }
    if (u === "/recipes/bulk-import/extract") {
      return Promise.resolve({
        ok: true,
        json: async () => ({ drafts: [draftA, draftB] }),
      } as Response);
    }
    if (u === "/recipes" && opts?.method === "POST") {
      const body = JSON.parse(String(opts.body));
      return Promise.resolve({
        ok: true,
        json: async () => ({ id: "new-id", ...body, ingredients: [] }),
      } as Response);
    }
    return Promise.reject(new Error(`Unexpected fetch: ${u}`));
  }) as jest.Mock;
});

afterEach(() => {
  jest.restoreAllMocks();
  localStorage.clear();
});

test("discover shows candidate count, extract loads the review queue, save/skip advance and summarize", async () => {
  render(<BulkRecipeImport onBack={() => {}} userProfile={{ is_admin: true }} />);

  fireEvent.change(screen.getByPlaceholderText("https://example.com/recipes/"), {
    target: { value: "https://example.com/recipes/" },
  });
  fireEvent.click(screen.getByText("Find Recipes"));

  await waitFor(() => {
    expect(screen.getByText("Found 2 candidate links on this page.")).toBeInTheDocument();
  });

  fireEvent.click(screen.getByText("Extract 2 Recipes"));

  await waitFor(() => {
    expect(screen.getByText("Recipe 1 of 2")).toBeInTheDocument();
  });
  expect(screen.getByDisplayValue("Chocolate Cake")).toBeInTheDocument();

  fireEvent.click(screen.getByText("Save & Next"));

  await waitFor(() => {
    expect(screen.getByText("Recipe 2 of 2")).toBeInTheDocument();
  });
  expect(screen.getByDisplayValue("Banana Bread")).toBeInTheDocument();

  fireEvent.click(screen.getByText("Skip & Next"));

  await waitFor(() => {
    expect(screen.getByText("Saved 1 of 2.")).toBeInTheDocument();
  });
});

test("zero extracted drafts shows a found-0 message instead of an empty saved-count summary", async () => {
  (global.fetch as jest.Mock).mockImplementation((url: RequestInfo | URL) => {
    const u = String(url);
    if (u === "/recipes/bulk-import/discover") {
      return Promise.resolve({
        ok: true,
        json: async () => ({ urls: ["https://example.com/recipes/chocolate-cake/"] }),
      } as Response);
    }
    if (u === "/recipes/bulk-import/extract") {
      return Promise.resolve({ ok: true, json: async () => ({ drafts: [] }) } as Response);
    }
    return Promise.reject(new Error(`Unexpected fetch: ${u}`));
  });

  render(<BulkRecipeImport onBack={() => {}} userProfile={{ is_admin: true }} />);

  fireEvent.change(screen.getByPlaceholderText("https://example.com/recipes/"), {
    target: { value: "https://example.com/recipes/" },
  });
  fireEvent.click(screen.getByText("Find Recipes"));

  await waitFor(() => {
    expect(screen.getByText("Found 1 candidate link on this page.")).toBeInTheDocument();
  });

  fireEvent.click(screen.getByText("Extract 1 Recipe"));

  await waitFor(() => {
    expect(screen.getByText("Found 0 recipes in that batch.")).toBeInTheDocument();
  });
  expect(screen.queryByText("Saved 0 of 0.")).not.toBeInTheDocument();
});

test("queue step pre-checks is_shared even though extracted drafts default it to false", async () => {
  render(<BulkRecipeImport onBack={() => {}} userProfile={{ is_admin: true }} />);

  fireEvent.change(screen.getByPlaceholderText("https://example.com/recipes/"), {
    target: { value: "https://example.com/recipes/" },
  });
  fireEvent.click(screen.getByText("Find Recipes"));

  await waitFor(() => {
    expect(screen.getByText("Found 2 candidate links on this page.")).toBeInTheDocument();
  });

  fireEvent.click(screen.getByText("Extract 2 Recipes"));

  await waitFor(() => {
    expect(screen.getByText("Recipe 1 of 2")).toBeInTheDocument();
  });

  const shareLabel = screen.getByText("Share in the shared recipe library");
  const toggle = shareLabel.closest(".recipe-shared-toggle") as HTMLElement;
  const checkbox = toggle.querySelector('input[type="checkbox"]') as HTMLInputElement;
  expect(checkbox.checked).toBe(true);
});

test("zero candidate links shows a message instead of an empty confirm screen", async () => {
  (global.fetch as jest.Mock).mockImplementationOnce((url: RequestInfo | URL) => {
    if (String(url) === "/recipes/bulk-import/discover") {
      return Promise.resolve({ ok: true, json: async () => ({ urls: [] }) } as Response);
    }
    return Promise.reject(new Error("unexpected"));
  });

  render(<BulkRecipeImport onBack={() => {}} userProfile={{ is_admin: true }} />);

  fireEvent.change(screen.getByPlaceholderText("https://example.com/recipes/"), {
    target: { value: "https://example.com/empty-page/" },
  });
  fireEvent.click(screen.getByText("Find Recipes"));

  await waitFor(() => {
    expect(
      screen.getByText("No recipe links found on that page — for a single recipe, use Import instead.")
    ).toBeInTheDocument();
  });
});
