# Hosted Backend Deployment — Design

## Problem

PakuPaku has no hosted deployment. Everything runs locally: a dev
Postgres, `uvicorn main:app --reload`, and `npm start` for the
frontend. This blocks two things directly:

- Anyone other than a developer running the repo locally can't use the
  app at all.
- The desktop (Electron) build's accounts are fully local-only, isolated
  per install — there's no shared identity to unify them with a web
  account, which is a prerequisite for fixing desktop's forgot-password
  (it currently can't send email at all — see the sibling "no SMTP
  reaches the packaged desktop app" finding from this session).

This spec covers only standing up the hosted deployment itself. Unifying
desktop accounts with a hosted account is deliberately **out of scope**
here — that's a separate, later piece of work this unblocks but doesn't
include.

## Goals / non-goals

- **Goal:** a real, reachable PakuPaku deployment — API + Postgres +
  static frontend — running continuously (with free-tier cold starts
  accepted as a tradeoff), reachable over HTTPS.
- **Goal:** stay genuinely free indefinitely, not free-until-a-trial-ends.
- **Goal:** no secrets ever committed to git — production config lives
  only in each platform's own env-var UI.
- **Non-goal:** desktop-app account unification (separate future spec).
- **Non-goal:** a real migration tool (Alembic etc.) for production
  schema changes. `create_all()` handles the empty-database initial
  deploy; future schema changes against the live production database
  are a known follow-up, called out below, not solved here.
- **Non-goal:** custom domain. Ship on the platforms' own subdomains
  first; a custom domain is a small, separable follow-up once this
  works.
- **Non-goal:** CI/CD pipeline beyond each platform's built-in
  git-push-to-deploy. No GitHub Actions in this pass.

## Architecture

```
Cloudflare Pages (React static build)
        │  fetch() calls, CORS
        ▼
Render free web service (FastAPI via uvicorn)
        │  asyncpg
        ▼
Neon (serverless Postgres, free tier)
```

- **Frontend — Cloudflare Pages.** Free static hosting, no cold starts,
  no card required. Builds `pakupaku-frontend` and serves the static
  output directly; no server-side code runs here.
- **API — Render free web service.** Runs `uvicorn main:app` directly
  (no Dockerfile — Render's native Python runtime is simpler for a
  plain ASGI app). Free tier sleeps after ~15 minutes idle; the next
  request pays a ~30-60s cold start. Acceptable for a personal project
  with sporadic traffic.
- **Database — Neon.** Free-tier serverless Postgres. Chosen over
  Render's own free Postgres, which Render deletes after a 30-day
  trial — a real trap for "keep it free," since the data would
  silently disappear. Neon's free tier autosuspends when idle but
  never deletes data.
- **Email — unchanged.** The app keeps talking directly to
  `smtp.gmail.com` using the existing Gmail App Password already
  configured for local dev. No new infrastructure.

`config.py` already reads every setting
(`DATABASE_URL`, `SECRET_KEY`, `SMTP_*`, `CORS_ALLOWED_ORIGINS`,
`FRONTEND_URL`, `USDA_API_KEY`) from environment variables with
working local-dev defaults — **no code changes are needed there**.
Production configuration is entirely a matter of setting the right
env vars in Render's dashboard; the code path is identical to local
dev.

## Repo changes

- **`requirements.txt`** — currently only lists the deps the recipe-import
  feature added (`beautifulsoup4`, `pytest`, `pytest-asyncio`); there has
  never been a full pinned requirements file for the app. This spec adds
  one covering every runtime dependency (`fastapi`, `uvicorn`,
  `sqlalchemy`, `asyncpg`, `aiosqlite`, `pydantic`, `python-jose`,
  `passlib`, `bcrypt`, `aiosmtplib`, `python-dotenv`,
  `python-multipart`, `beautifulsoup4`), pinned to the versions already
  proven working in this repo's dev venv. (`fastapi-users` is installed
  in the dev venv but unused by any code — confirmed via `grep` — and is
  excluded.)
- **`.env.example`** — documents every env var Render/Neon need set,
  without real values, so the deploy runbook has a single source of
  truth for what to paste where.
- **Start command** — `uvicorn main:app --host 0.0.0.0 --port $PORT`,
  documented in the runbook (Render's dashboard field, not a repo file).
- **`CORS_ALLOWED_ORIGINS` / `FRONTEND_URL`** — set on Render to the real
  Cloudflare Pages URL once it exists; `localhost:3000` stays reachable
  too since that's already `config.py`'s default fallback.

No other application code changes. This is infrastructure-and-config
work, not a feature.

## Schema on first deploy

Neon starts empty. The existing `create_all()` pattern (already used
elsewhere in this app — see `database.py` / the desktop build's
`backend_entry.py`) creates every table on first boot against the new,
empty database. This is sufficient for a first deploy and needs no new
code.

**Known follow-up, explicitly not solved here:** the same gap this
session just fixed for the desktop SQLite build — `create_all()` only
creates missing *tables*, never adds columns to existing ones — applies
identically to this new production Postgres once it's live. Every future
model change will need either a manual `ALTER TABLE` against Neon (the
same way the desktop SQLite database was hand-patched this session) or a
real migration tool. Deferred to a future spec; flagged here so it isn't
forgotten.

## Division of labor

Account creation and clicking "deploy" on third-party services are
actions the assistant does not take on the user's behalf.

- **Assistant prepares:** `requirements.txt`, `.env.example`, the exact
  Render build/start commands, and a step-by-step runbook (create Neon
  project → copy connection string → create Render web service → paste
  env vars → create Cloudflare Pages project → point it at the frontend
  build → set `CORS_ALLOWED_ORIGINS`/`FRONTEND_URL` to match). A fresh
  `SECRET_KEY` is generated and handed to the user to paste in directly
  — never written to a file or committed.
- **User performs:** signs up for Render / Neon / Cloudflare Pages (all
  free, no card required for the tiers used here), connects the GitHub
  repo, and pastes in the env vars from the runbook
  (`DATABASE_URL` from Neon, the generated `SECRET_KEY`, the existing
  `SMTP_USER`/`SMTP_PASSWORD`/`USDA_API_KEY`).

Secrets never touch git at any point — production values live only in
Render's and Cloudflare's own env-var UIs, the same boundary `.env`
already draws for local dev.

## Testing

There's no automated test for "is the deployment reachable" — this is
infrastructure, not application logic, and the existing pytest suite
(51 tests, backend logic) already covers the application code untouched
by this work. Verification here is manual, post-deploy:

- [ ] Register a real account against the hosted API from the deployed
      frontend
- [ ] Full login → onboarding → dashboard flow against Neon
- [ ] A cold-start request after ~20 min idle succeeds (confirms the
      free-tier sleep/wake cycle works, not just a warm server)
- [ ] Verification email and forgot-password email both arrive
      (confirms SMTP works from Render's network, not just localhost)
- [ ] CORS: requests from the Cloudflare Pages origin succeed; a
      request from an arbitrary other origin is rejected
