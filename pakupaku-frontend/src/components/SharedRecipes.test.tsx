import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import SharedRecipes from "./SharedRecipes";

const sharedRecipe = {
  id: "11111111-1111-1111-1111-111111111111",
  name: "Shared Soup",
  servings: 2,
  image_url: null,
  diet_tags: ["vegan", "gluten_free"],
  total_calories: 200,
  total_protein_g: 10,
  total_fat_g: 5,
  total_carbs_g: 20,
};

beforeEach(() => {
  localStorage.setItem("token", "test-token");
  global.fetch = jest.fn((url: RequestInfo | URL, init?: RequestInit) => {
    const u = String(url);
    if (u === "/recipes/shared") {
      return Promise.resolve({ ok: true, json: async () => [sharedRecipe] } as Response);
    }
    if (u === `/recipes/${sharedRecipe.id}/copy` && init?.method === "POST") {
      return Promise.resolve({ ok: true, json: async () => ({ ...sharedRecipe, id: "copy-id", is_shared: false }) } as Response);
    }
    if (u === "/logs" && init?.method === "POST") {
      return Promise.resolve({ ok: true, json: async () => ({ id: "log-id" }) } as Response);
    }
    return Promise.reject(new Error(`Unexpected fetch: ${u}`));
  }) as jest.Mock;
});

afterEach(() => {
  jest.restoreAllMocks();
  localStorage.clear();
});

test("lists shared recipes and their diet tags", async () => {
  render(<SharedRecipes onBack={() => {}} />);
  await waitFor(() => {
    expect(screen.getByText("Shared Soup")).toBeInTheDocument();
  });
  expect(screen.getByText("vegan")).toBeInTheDocument();
  expect(screen.getByText("gluten free")).toBeInTheDocument();
});

test("save a copy calls the copy endpoint", async () => {
  render(<SharedRecipes onBack={() => {}} />);
  await waitFor(() => screen.getByText("Shared Soup"));

  fireEvent.click(screen.getByText("Save a copy"));

  await waitFor(() => {
    expect(global.fetch).toHaveBeenCalledWith(
      `/recipes/${sharedRecipe.id}/copy`,
      expect.objectContaining({ method: "POST" })
    );
  });
});

test("log now posts to /logs with the recipe id and scaled nutrients", async () => {
  render(<SharedRecipes onBack={() => {}} />);
  await waitFor(() => screen.getByText("Shared Soup"));

  fireEvent.click(screen.getByText("Log now"));
  fireEvent.click(screen.getByText("Confirm"));

  await waitFor(() => {
    expect(global.fetch).toHaveBeenCalledWith(
      "/logs",
      expect.objectContaining({ method: "POST" })
    );
  });
  const call = (global.fetch as jest.Mock).mock.calls.find(([u]) => u === "/logs");
  const body = JSON.parse(call[1].body);
  expect(body.recipe_id).toBe(sharedRecipe.id);
  expect(body.calories).toBe(200); // 1 serving, default multiplier
});
