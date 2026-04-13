# PakuPaku

PakuPaku is an inclusive nutrition-tracking app with three main parts:

- A FastAPI backend for auth, user profiles, recipes, logs, measurements, and USDA food lookups.
- A React frontend in `pakupaku-frontend/`.
- An Electron packaging layer that bundles the frontend and launches the backend for desktop builds.

For a deeper walkthrough, see [docs/architecture.md](/Users/hanniamabellopezmontano/projects/pakupaku/pakupaku/docs/architecture.md).

## Repository Layout

- `main.py`: FastAPI app and route handlers.
- `auth.py`: password hashing, JWT creation, and current-user dependency.
- `database.py`: async SQLAlchemy engine, session factory, and `get_db()` dependency.
- `models.py`: SQLAlchemy ORM models.
- `schemas.py`: Pydantic request/response schemas.
- `nutrition_calculator.py`: calorie, body-fat, and macro calculations used by onboarding.
- `usda.py`: USDA FoodData Central client and nutrient extraction helpers.
- `email_utils.py`: verification email sending.
- `backend_entry.py`: desktop backend bootstrap used by packaged builds.
- `pakupaku-frontend/`: web/mobile frontend.

## Backend Overview

The API is defined in `main.py` and organized by route groups:

- `/auth`: registration, login, email verification, resend verification.
- `/users`: current profile, preferences, onboarding calculations, custom goals.
- `/foods`: USDA search, detail, and bulk lookup.
- `/logs`: food log creation, listing, deletion, and daily summary.
- `/recipes`: custom recipe CRUD.
- `/measurements`: body measurement tracking.

Most routes follow the same pattern:

1. FastAPI validates the request body or query parameters using `schemas.py`.
2. Auth-protected routes resolve the user through `get_current_user()` in `auth.py`.
3. The route reads or writes SQLAlchemy models using an async session from `get_db()`.
4. `database.get_db()` commits at the end of a successful request or rolls back on error.

## Frontend Overview

The frontend currently contains two data access styles:

- Backend-backed React app code that calls the FastAPI API with `fetch()`.
- Local/mobile-oriented service modules under `pakupaku-frontend/src/services/` that use SQLite and direct USDA requests.

The entry point is `pakupaku-frontend/src/App.tsx`, which decides whether the user sees:

- login
- email verification
- onboarding
- dashboard
- recipe builder

See the frontend-specific guide in [pakupaku-frontend/README.md](/Users/hanniamabellopezmontano/projects/pakupaku/pakupaku/pakupaku-frontend/README.md).

## Environment Variables

Important backend environment variables:

- `DATABASE_URL`: SQLAlchemy connection string.
- `SECRET_KEY`: JWT signing key.
- `FRONTEND_URL`: URL used for email verification redirects.
- `BACKEND_PUBLIC_URL`: public backend base URL used in verification links.
- `CORS_ALLOWED_ORIGINS`: comma-separated list of allowed browser origins.
- `USDA_API_KEY`: USDA FoodData Central API key.
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`: email settings.

Desktop builds use `backend_entry.py` to set desktop-specific environment values before importing the app.

## Running the Project

Backend:

```bash
uvicorn main:app --reload
```

Frontend:

```bash
cd pakupaku-frontend
npm start
```

Electron shell from the repo root:

```bash
npm run dev
```

## Where To Make Changes

- Add or modify API endpoints: `main.py`
- Change validation rules or response payloads: `schemas.py`
- Change persistence shape: `models.py`
- Change auth behavior: `auth.py`
- Change nutrition logic: `nutrition_calculator.py`
- Change USDA parsing or API behavior: `usda.py`
- Change email verification flow: `email_utils.py`, `main.py`, and `pakupaku-frontend/src/App.tsx`
- Change frontend screens: `pakupaku-frontend/src/components/`

## Current Caveats

- The frontend code mixes backend API usage with local SQLite/mobile service abstractions, so not every path shares the same data flow.
- The repo still contains generated artifacts from earlier work; `.gitignore` is now stricter, but already-tracked generated files may still exist in history or the current index.
