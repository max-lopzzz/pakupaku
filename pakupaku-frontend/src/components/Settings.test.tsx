import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import Settings from "./Settings";

beforeEach(() => {
  localStorage.setItem("token", "t");
});
afterEach(() => {
  jest.restoreAllMocks();
  localStorage.clear();
});

test("dietary preferences: pre-checked, editable, saved", async () => {
  const patched: any[] = [];
  global.fetch = jest.fn((url: RequestInfo | URL, init?: RequestInit) => {
    const u = String(url);
    if (u.endsWith("/users/me") && init?.method === "PATCH") {
      patched.push(JSON.parse(String(init.body)));
      return Promise.resolve({ ok: true, json: async () => ({}) } as Response);
    }
    return Promise.resolve({ ok: true, json: async () => ({}) } as Response);
  }) as jest.Mock;

  render(
    <Settings
      onBack={() => {}}
      onLogout={() => {}}
      onProfileUpdate={() => {}}
      userProfile={{ diet_tags: ["vegan"], safe_mode: false }}
    />,
  );

  const vegan = screen.getByLabelText("vegan") as HTMLInputElement;
  expect(vegan.checked).toBe(true);

  fireEvent.click(screen.getByLabelText("keto"));
  fireEvent.click(screen.getByText("Save dietary preferences"));

  await waitFor(() => expect(patched.length).toBe(1));
  expect(patched[0].diet_tags.sort()).toEqual(["keto", "vegan"]);
});
