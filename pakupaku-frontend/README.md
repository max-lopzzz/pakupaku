# PakuPaku Frontend

This folder contains the React frontend for PakuPaku.

## What Lives Here

- `src/App.tsx`: top-level app state and view routing.
- `src/components/`: major screens and screen-specific CSS.
- `src/services/api.ts`: higher-level data helpers used by parts of the app.
- `src/services/auth.ts`: local SQLite-backed auth/session logic for device-first flows.
- `src/services/db.ts`: Capacitor SQLite database setup.
- `src/services/healthkit.ts`: HealthKit integration helpers.
- `src/services/nutritionCalculator.ts`: frontend copies of nutrition calculation helpers.

## Important Architectural Note

The frontend currently mixes two patterns:

- direct `fetch()` calls to the FastAPI backend
- local service-layer access through SQLite-oriented modules in `src/services/`

That means not every screen follows the same data path yet. Before changing a feature, check whether it is:

- backend-driven
- device-local
- shared across both

## Main Screens

- `Login.tsx`: login and registration form.
- `Onboarding.tsx`: nutrition setup flow.
- `Dashboard.tsx`: logging, summaries, recipes, and measurements.
- `RecipeBuilder.tsx`: create/edit recipes.
- `Settings.tsx`: account settings, safe mode, export, and deletion.

## Running Locally

```bash
npm start
```

The dev server runs on `http://localhost:3000`.

This project is configured with:

- CRA dev server
- proxy to `http://localhost:8000` for backend API requests

So the FastAPI backend should also be running if you want the backend-backed flows to work.

## Other Useful Commands

```bash
npm test
npm run build
npm run build:ios
npm run build:android
```

## File Navigation Tips

- Change route/view selection behavior: `src/App.tsx`
- Change dashboard UI: `src/components/Dashboard.tsx`
- Change onboarding logic or payloads: `src/components/Onboarding.tsx`
- Change local SQLite schema: `src/services/db.ts`
- Change local auth/session behavior: `src/services/auth.ts`
- Change USDA lookup behavior used by service-layer flows: `src/services/api.ts`

## Frontend Caveats

- There is still a fair amount of `any` in the TypeScript code, so types are not yet acting as strong guardrails.
- Some calculations exist both in Python and TypeScript, which can drift if one side is updated without the other.
- Some flows assume a server token in `localStorage`, while others assume a local device session model.
