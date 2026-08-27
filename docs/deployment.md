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
   scheme from `postgresql://` to `postgresql+asyncpg://`, keeping
   everything else the same. Save this rewritten string — it's the
   `DATABASE_URL` value for step 2.

## 2. Render — API

1. Sign up at https://render.com (GitHub sign-in recommended — it also
   makes connecting the repo in the next step a one-click picker).
2. New → Web Service → connect the `pakupaku` GitHub repo.
3. Settings:
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - **Instance Type:** Free
4. Environment variables — open `.env.example` in this repo and add
   each name as a Render env var with a real value:
   - `DATABASE_URL` — the rewritten Neon string from step 1.4
   - `SECRET_KEY` — generate with
     `python3 -c "import secrets; print(secrets.token_hex(32))"` on your
     own machine; paste the output. Do not reuse any local-dev value.
   - `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` — same Gmail
     App Password already used for local dev.
   - `USDA_API_KEY` — your existing key.
   - `FRONTEND_URL`, `CORS_ALLOWED_ORIGINS`, `BACKEND_PUBLIC_URL` —
     leave these for now; you'll fill them in during step 3, once the
     Cloudflare Pages URL and this Render service's own URL both exist.
     (Render assigns this service's public URL immediately on first
     deploy, e.g. `https://pakupaku-api.onrender.com` — visible at the
     top of the service's dashboard page.)
5. Deploy. First build installs `requirements.txt` and starts uvicorn.
   Watch the deploy log for `Application startup complete` — that
   confirms `create_all()` ran and the app is serving.
6. Sanity check from your own machine:
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
   build. Set an environment variable on the Cloudflare Pages project:
   `REACT_APP_API_URL` = your Render URL from step 2. (This requires one
   small code change this plan doesn't cover — see the note at the
   bottom of this file.)
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
