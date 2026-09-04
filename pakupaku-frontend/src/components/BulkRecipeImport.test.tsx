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
        food_id: "gen:00111",
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

function makeUrls(n: number): string[] {
  return Array.from({ length: n }, (_, i) => `https://example.com/recipes/r${i + 1}/`);
}

function draftForUrl(url: string) {
  const n = url.match(/r(\d+)/)![1];
  return {
    name: `Recipe ${n}`,
    servings: 4,
    image_url: null,
    source_url: url,
    instructions: null,
    ingredients: [],
  };
}

test("extraction runs in chunks and the progress bar advances as each chunk finishes", async () => {
  const urls = makeUrls(30);
  let extractCalls = 0;
  let releaseSecondChunk: () => void = () => {};
  const secondChunkGate = new Promise<void>(resolve => {
    releaseSecondChunk = resolve;
  });

  (global.fetch as jest.Mock).mockImplementation((url: RequestInfo | URL, opts?: RequestInit) => {
    const u = String(url);
    if (u === "/recipes/bulk-import/discover") {
      return Promise.resolve({ ok: true, json: async () => ({ urls }) } as Response);
    }
    if (u === "/recipes/bulk-import/extract") {
      extractCalls += 1;
      const body = JSON.parse(String(opts!.body)) as { urls: string[] };
      const drafts = body.urls.map(draftForUrl);
      if (extractCalls === 1) {
        return Promise.resolve({ ok: true, json: async () => ({ drafts }) } as Response);
      }
      return secondChunkGate.then(
        () => ({ ok: true, json: async () => ({ drafts }) } as Response),
      );
    }
    return Promise.reject(new Error(`Unexpected fetch: ${u}`));
  });

  render(<BulkRecipeImport onBack={() => {}} userProfile={{ is_admin: true }} />);
  fireEvent.change(screen.getByPlaceholderText("https://example.com/recipes/"), {
    target: { value: "https://example.com/recipes/" },
  });
  fireEvent.click(screen.getByText("Find Recipes"));
  await waitFor(() => {
    expect(screen.getByText("Found 30 candidate links on this page.")).toBeInTheDocument();
  });

  fireEvent.click(screen.getByText("Extract 30 Recipes"));

  // First chunk (15) resolved, second still pending: the bar sits at 15/30.
  await waitFor(() => {
    expect(screen.getByText("Processing 15 of 30 links…")).toBeInTheDocument();
  });
  expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "50");

  releaseSecondChunk();

  await waitFor(() => {
    expect(screen.getByText("Recipe 1 of 30")).toBeInTheDocument();
  });
  expect(extractCalls).toBe(2);
});

test("a failed chunk keeps the earlier chunk's drafts and offers them for review", async () => {
  const urls = makeUrls(30);
  let extractCalls = 0;

  (global.fetch as jest.Mock).mockImplementation((url: RequestInfo | URL, opts?: RequestInit) => {
    const u = String(url);
    if (u === "/recipes/bulk-import/discover") {
      return Promise.resolve({ ok: true, json: async () => ({ urls }) } as Response);
    }
    if (u === "/recipes/bulk-import/extract") {
      extractCalls += 1;
      if (extractCalls === 1) {
        const body = JSON.parse(String(opts!.body)) as { urls: string[] };
        return Promise.resolve({
          ok: true,
          json: async () => ({ drafts: body.urls.map(draftForUrl) }),
        } as Response);
      }
      return Promise.resolve({
        ok: false,
        json: async () => ({ detail: "extraction failed" }),
      } as Response);
    }
    return Promise.reject(new Error(`Unexpected fetch: ${u}`));
  });

  render(<BulkRecipeImport onBack={() => {}} userProfile={{ is_admin: true }} />);
  fireEvent.change(screen.getByPlaceholderText("https://example.com/recipes/"), {
    target: { value: "https://example.com/recipes/" },
  });
  fireEvent.click(screen.getByText("Find Recipes"));
  await waitFor(() => {
    expect(screen.getByText("Found 30 candidate links on this page.")).toBeInTheDocument();
  });

  fireEvent.click(screen.getByText("Extract 30 Recipes"));

  await waitFor(() => {
    expect(screen.getByText(/stopped early/i)).toBeInTheDocument();
  });

  fireEvent.click(screen.getByText("Review 15 recipes"));

  await waitFor(() => {
    expect(screen.getByText("Recipe 1 of 15")).toBeInTheDocument();
  });
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
