# Deploying PakuPaku

One-time setup to stand up a free, always-reachable PakuPaku deployment:
Neon (Postgres) → Render (API) → Cloudflare Pages (frontend). Total
cost: $0. No credit card required for any of the three services at the
tiers used here.

Do these in order — each later step needs a value from the one before it.

## 1. Neon — database

1. Sign up at https://neon.tech (GitHub sign-in is fastest).
2. Create a new project. Any region close to you is fine; the free tier
   doesn't offer much regional choice anyway.
3. Neon shows a connection string on project creation, shaped like
   `postgresql://<user>:<password>@<host>/<dbname>?sslmode=require`.
   Copy it — you'll paste it into Render next.
4. This app's `DATABASE_URL` needs the `+asyncpg` driver marker, which
   Neon's own connection string doesn't include by default. Rewrite the
   scheme from `postgresql://` to `postgresql+asyncpg://`, **and also
   remove the `?sslmode=require` query string entirely** — SQLAlchemy's
   asyncpg dialect passes the URL's query string straight into
   `asyncpg.connect(**opts)`, and asyncpg's `connect()` has no
   `sslmode` keyword argument, so leaving it in crashes the very first
   query with `TypeError: connect() got an unexpected keyword argument
   'sslmode'`. Dropping it is safe: asyncpg negotiates TLS to Neon
   automatically, and Neon requires TLS on all connections regardless
   of whether `sslmode` is present in the URL.

   Before (Neon's default string):
   ```
   postgresql://alice:s3cr3t@ep-cool-lab-123456.us-east-2.aws.neon.tech/neondb?sslmode=require
   ```
   After (this app's `DATABASE_URL`):
   ```
   postgresql+asyncpg://alice:s3cr3t@ep-cool-lab-123456.us-east-2.aws.neon.tech/neondb
   ```

   Save this rewritten string — it's the `DATABASE_URL` value for step 2.

## 2. Render — API

1. Sign up at https://render.com (GitHub sign-in recommended — it also
   makes connecting the repo in the next step a one-click picker).
2. New → Web Service → connect the `pakupaku` GitHub repo.
3. Settings:
   - **Branch:** `main`
   - **Root Directory:** leave blank. `main.py` and `requirements.txt`
     live at the repo root, not in a subdirectory — do not type `main`
     here by mistake (that's the branch, a separate field above); doing
     so fails the clone step with "Root directory 'main' does not
     exist."
   - **Runtime:** Python 3
   - **Build Command:** see step 5 below — it extends the plain
     `pip install -r requirements.txt` command with a schema-creation
     step, since Render's Pre-Deploy Command field (the more natural
     place for this) is a paid-instance-only feature.
   - **Start Command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - **Instance Type:** Free
4. Environment variables — open `.env.example` in this repo and add
   each name as a Render env var with a real value:
   - `DATABASE_URL` — the rewritten Neon string from step 1.4
   - `SECRET_KEY` — generate with
     `python3 -c "import secrets; print(secrets.token_hex(32))"` on your
     own machine; paste the output. Do not reuse any local-dev value.
   - `RESEND_API_KEY`, `RESEND_FROM_EMAIL` — sign up free at
     https://resend.com and get an API key from the dashboard. Direct
     SMTP (the original design) doesn't work here: Render's free tier
     blocks outbound SMTP entirely to prevent spam abuse (confirmed
     live — registration succeeded but email sending failed with
     `SMTPConnectTimeoutError`); Resend's API is plain HTTPS, which
     isn't blocked. `RESEND_FROM_EMAIL` can stay at its default
     (`PakuPaku <onboarding@resend.dev>`, Resend's shared sender —
     works immediately, no domain verification needed).
   - `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL` — optional. Only needed
     for the recipe-import LLM fallback path (used when a blog page
     lacks schema.org/JSON-LD Recipe markup); that path returns a 503
     if these are unset, but everything else in the app works fine
     without them.
   - `PYTHON_VERSION` = `3.8.19` — pins Render's build to the same
     Python version `requirements.txt`'s pinned package versions were
     validated against, instead of whatever default interpreter Render
     would otherwise pick.
   - `FRONTEND_URL`, `CORS_ALLOWED_ORIGINS`, `BACKEND_PUBLIC_URL` —
     leave these for now; you'll fill them in during step 3, once the
     Cloudflare Pages URL and this Render service's own URL both exist.
     (Render assigns this service's public URL immediately on first
     deploy, e.g. `https://pakupaku-api.onrender.com` — visible at the
     top of the service's dashboard page.)
5. Build Command — this app has no lifespan hook that creates database
   tables (that logic only exists in `backend_entry.py`, used by the
   desktop build), so without an extra step the API would boot fine
   against a fresh Neon database but the first `/auth/register` call
   would fail with `relation "users" does not exist`.

   Render's Pre-Deploy Command field is the natural place for a
   once-per-deploy setup step like this, but it's a **paid-instance-only
   feature** — not available on the Free tier this runbook uses. Fold
   the same logic into the **Build Command** field instead (available on
   every tier, and Render exposes the service's configured env vars,
   including `DATABASE_URL`, to the build step just like it does at
   runtime):
   ```
   pip install -r requirements.txt && python3 create_tables.py && python3 seed_foods.py
   ```
   `create_tables.py` (in this repo) mirrors the same `create_all()`
   pattern `backend_entry.py` already uses for the desktop build. An
   inline multi-line `python3 -c "..."` string is tempting here but
   fragile in practice — Render's Build Command field collapses embedded
   newlines, breaking Python's indentation-sensitive syntax with an
   `IndentationError`. A real script file sidesteps that entirely, which
   is why this repo has one instead. It creates the schema on Neon
   (empty on first deploy) and is safe to leave configured permanently:
   `create_all()` only creates tables that don't already exist, so it's
   a no-op on every build after the first — the tradeoff versus a true
   Pre-Deploy Command is that this now reruns on every deploy rather than
   once, which costs a fraction of a second and nothing else.

   `seed_foods.py` is a no-op until `data/foods.sqlite` is committed; once
   present, it replaces the `foods` table contents on every deploy.
6. Deploy. The build step above installs `requirements.txt` and creates
   the schema in one command, then Render starts uvicorn per the Start
   Command. The build step exiting successfully is what confirms the
   schema was created — watch for it to complete without error in the
   build log. Seeing `Application startup complete` afterward only
   confirms uvicorn itself started serving; it says nothing about the
   tables.
7. Sanity check from your own machine:
   `curl https://<your-render-url>/docs` should return the FastAPI
   Swagger UI HTML, not an error page.

## 3. Cloudflare Pages — frontend

1. Sign up at https://pages.cloudflare.com (or your existing Cloudflare
   account if you have one).
2. Create a project → connect the same GitHub repo.
3. Build settings:
   - **Framework preset:** Create React App
   - **Root directory:** `pakupaku-frontend`
   - **Build command:** `npm run build`
   - **Build output directory:** `build`
4. Before the first build, the frontend needs to know the Render API's
   URL. This repo's `pakupaku-frontend/package.json` uses a `"proxy"`
   field for local dev only — that doesn't apply to a production static
   build. Set environment variables on the Cloudflare Pages project:
   - `REACT_APP_API_URL` = your Render URL from step 2. (This requires
     one small code change this plan doesn't cover — see the note at
     the bottom of this file.)
   - `NODE_VERSION` = `20` — pins the build to a Node version known to
     work with `react-scripts` 5.0.1, instead of whatever default
     Cloudflare Pages would otherwise pick. (Unlike `PYTHON_VERSION` in
     section 2, this isn't independently verified against this exact
     dev environment — `pakupaku-frontend/package.json` has no
     `engines` field to pin from — it's a reasonable current-LTS
     default.)
5. Deploy. Cloudflare assigns a URL like
   `https://pakupaku.pages.dev`.

## 4. Wire CORS back together

Now that both URLs exist:

1. Back in Render's dashboard, set the env vars you left blank in step 2:
   - `FRONTEND_URL` = the Cloudflare Pages URL from step 3.5
   - `CORS_ALLOWED_ORIGINS` = the same URL
   - `BACKEND_PUBLIC_URL` = this Render service's own URL
2. Render redeploys automatically when env vars change. Wait for that
   redeploy to finish before testing.

## 5. Verify

- [ ] Open the Cloudflare Pages URL, register a real account
- [ ] Confirm the verification email arrives (from the same Gmail
      address used for local dev)
- [ ] Log in, complete onboarding, reach the dashboard
- [ ] Trigger forgot-password, confirm that email arrives too
- [ ] Wait ~20 minutes idle, then make a request — confirm it succeeds
      after the free-tier cold-start delay (don't confuse a slow first
      response with a broken deployment)
- [ ] CORS actually restricts: from a browser console on a different
      origin, or via
      `curl -H "Origin: https://example.com" https://<your-render-url>/docs`,
      confirm the response lacks an `Access-Control-Allow-Origin`
      header for that origin (a request from the real Cloudflare Pages
      origin succeeding isn't enough on its own — it doesn't rule out
      CORS being wide open to everyone)

## Known gap this doesn't solve

`create_all()` creates tables on first deploy but can't add columns to
tables that already exist. The first deploy is fine — Neon starts
empty. Every schema change *after* that will need a manual `ALTER
TABLE` against Neon (the same way this session hand-patched the desktop
SQLite database), until a real migration tool is added. Out of scope
for this deployment; tracked as follow-up work.

## Note: `REACT_APP_API_URL` needs one small frontend change

Step 3.4 above references a `REACT_APP_API_URL` build-time variable
that the frontend doesn't currently read — every component calls
`fetch("/users/me")` etc. with a relative path, relying on
`package.json`'s dev-only `"proxy"` field. That field has no effect in
a production static build; Cloudflare would serve `fetch("/users/me")`
against Cloudflare's own domain, not Render, and every request would
404.

This is a real code change (reading `process.env.REACT_APP_API_URL` and
prefixing every `fetch()` call, or introducing a small fetch wrapper),
and it's outside this plan's scope, which was infrastructure/config
only. **Do this as a small follow-up bounded task before Cloudflare
Pages can actually work end-to-end** — flag it to the user rather than
skipping silently.
