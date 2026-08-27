/**
 * apiBase.ts
 * ----------
 * Every component talks to the backend with a relative path
 * (fetch("/users/me"), etc.), relying on package.json's "proxy" field to
 * route that to the dev backend during `npm start`. That field only
 * affects the dev server — a production static build (Cloudflare Pages)
 * has no proxy, so a relative fetch() resolves against the static host's
 * own origin instead of the API and 404s.
 *
 * REACT_APP_API_URL is a Create React App build-time env var: baked into
 * the static bundle at `npm run build`, empty by default. Locally that
 * keeps every call relative (unchanged dev behavior, still routed by the
 * proxy field); in production it's set to the real API's URL.
 */

export const API_BASE_URL = process.env.REACT_APP_API_URL ?? "";

/** fetch() with API_BASE_URL prefixed onto a relative path. Use this for
 *  every backend call instead of the bare global fetch(). */
export function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  return fetch(`${API_BASE_URL}${path}`, init);
}
