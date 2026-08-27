import { render, screen } from "@testing-library/react";
import Dashboard from "./Dashboard";

const nutritionData = {
  calories: { consumed: 0, goal: 2000 },
  protein: { consumed: 0, goal: 100 },
  carbs: { consumed: 0, goal: 250 },
  fat: { consumed: 0, goal: 70 },
};

beforeEach(() => {
  localStorage.setItem("token", "test-token");
  global.fetch = jest.fn((url: RequestInfo | URL) => {
    const u = String(url);
    if (u === "/recipes") {
      return Promise.resolve({ ok: true, json: async () => [] } as Response);
    }
    if (u.startsWith("/logs?log_date=")) {
      return Promise.resolve({ ok: true, json: async () => [] } as Response);
    }
    if (u === "/measurements") {
      return Promise.resolve({ ok: true, json: async () => [] } as Response);
    }
    return Promise.reject(new Error(`Unexpected fetch: ${u}`));
  }) as jest.Mock;
});

afterEach(() => {
  jest.restoreAllMocks();
  localStorage.clear();
});

test("Bulk Import button only appears for admins", () => {
  const { rerender } = render(
    <Dashboard
      nutritionData={nutritionData}
      userProfile={{ is_admin: false }}
      onOpenRecipeBuilder={() => {}}
      onOpenSettings={() => {}}
      onOpenSharedRecipes={() => {}}
      onOpenBulkImport={() => {}}
    />
  );
  expect(screen.queryByText("Bulk Import")).not.toBeInTheDocument();

  rerender(
    <Dashboard
      nutritionData={nutritionData}
      userProfile={{ is_admin: true }}
      onOpenRecipeBuilder={() => {}}
      onOpenSettings={() => {}}
      onOpenSharedRecipes={() => {}}
      onOpenBulkImport={() => {}}
    />
  );
  expect(screen.getByText("Bulk Import")).toBeInTheDocument();
});
