# Hosted Backend Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Task 4 is explicitly excluded from subagent dispatch — see its header.**

**Goal:** Produce the repo artifacts a hosted PakuPaku deployment needs (pinned `requirements.txt`, `.env.example`, a deployment runbook), then execute that runbook live with the user to stand up Neon (Postgres) → Render (API) → Cloudflare Pages (frontend), all on free tiers, with no secrets ever committed to git.

**Architecture:** Cloudflare Pages serves the static React build; it calls a Render-hosted FastAPI service over HTTPS; that service talks to a Neon Postgres database via `asyncpg`. `config.py` already reads all settings from environment variables — no application code changes are needed, only new config-describing files and the deploy itself.

**Tech Stack:** FastAPI, SQLAlchemy (async, `asyncpg`), Render (Python native runtime, no Dockerfile), Neon (serverless Postgres), Cloudflare Pages (static hosting).

**Spec:** [docs/superpowers/specs/2026-08-27-hosted-deployment-design.md](../specs/2026-08-27-hosted-deployment-design.md)

## Global Constraints

- No secrets are ever committed to git — `.env.example` documents variable *names* only, never real values.
- `requirements.txt` versions must match what's already proven working in this repo's dev venv (pinned exactly, not "latest").
- No changes to `config.py` or any other application code — this plan is infrastructure and documentation only.
- Desktop-account unification and a production migration tool are explicitly out of scope (see spec's Non-goals).
- Free tiers only: Render free web service, Neon free tier, Cloudflare Pages free tier. No paid upgrades in this pass.

---

### Task 1: Write a complete pinned `requirements.txt`

**Files:**
- Modify: `requirements.txt` (currently only lists recipe-import-feature deps; replace with the full app's runtime dependencies)

**Interfaces:**
- Consumes: nothing (first task)
- Produces: `requirements.txt` at repo root — Task 4's Render setup step points Render's build command at this file (`pip install -r requirements.txt`)

The app's direct third-party runtime imports (confirmed via `grep -hoE "^(import|from) [a-zA-Z_]+" main.py schemas.py models.py database.py config.py auth.py email_utils.py usda.py recipe_import.py nutrition_calculator.py`) are: `fastapi`, `uvicorn` (run command, not directly imported but required to serve), `sqlalchemy`, `asyncpg` (the Postgres driver `sqlalchemy` needs for `postgresql+asyncpg://` URLs — not directly imported either, but required), `pydantic`, `python-jose` (imported as `jose`), `passlib`, `bcrypt` (passlib's hashing backend, configured in `auth.py`'s `CryptContext(schemes=["bcrypt"])`), `aiosmtplib`, `python-dotenv` (imported as `dotenv`), `beautifulsoup4` (imported as `bs4`), `httpx`.

`python-multipart` is **not** needed — confirmed via `grep -n "Form(\|UploadFile\|OAuth2PasswordRequestForm" main.py` returning nothing; the app takes JSON bodies everywhere, no form parsing. `fastapi-users` is installed in the dev venv but unused by any code (`grep -rn "fastapi_users" --include="*.py" .` returns nothing) — leftover cruft, excluded.

- [ ] **Step 1: Replace `requirements.txt` with the full pinned list**

```
# Full runtime dependencies for the PakuPaku FastAPI backend.
# Versions pinned to what's proven working in this repo's dev venv.

fastapi==0.124.4
uvicorn==0.33.0
sqlalchemy==2.0.49
asyncpg==0.30.0
pydantic==2.10.6
python-jose==3.4.0
passlib==1.7.4
bcrypt==4.1.2
aiosmtplib==3.0.2
python-dotenv==1.0.1
beautifulsoup4==4.15.0
httpx==0.28.1

# Test-only, kept here so `pip install -r requirements.txt` alone is
# enough to run the suite locally.
pytest==8.3.5
pytest-asyncio==0.24.0
```

- [ ] **Step 2: Verify a clean install actually boots the app**

```bash
python3 -m venv /tmp/pakupaku-req-check
/tmp/pakupaku-req-check/bin/pip install -q -r requirements.txt
DATABASE_URL="postgresql+asyncpg://x@localhost/x" SECRET_KEY="test" \
  /tmp/pakupaku-req-check/bin/python3 -c "import main; print('OK')"
```

Expected: prints `OK` with no `ModuleNotFoundError`. (This doesn't need a
reachable Postgres — `main.py` only builds the async engine at import
time, it doesn't connect.)

- [ ] **Step 3: Verify the test suite passes against this exact dependency set**

```bash
DATABASE_URL="postgresql+asyncpg://x@localhost/x" SECRET_KEY="test" \
  /tmp/pakupaku-req-check/bin/python3 -m pytest -q
```

Expected: `51 passed` (matching the count from this repo's existing dev
venv — if the number differs, something in this pinned set behaves
differently than dev; investigate before continuing).

- [ ] **Step 4: Clean up and commit**

```bash
rm -rf /tmp/pakupaku-req-check
git add requirements.txt
git commit -m "Write a complete pinned requirements.txt for the hosted deployment

requirements.txt previously only listed deps the recipe-import feature
added — there was never a full pinned list for the app. This one covers
every runtime dependency, pinned to versions already proven working in
this repo's dev venv, so Render's build step (pip install -r
requirements.txt) produces the same environment. Excludes
python-multipart (no form parsing anywhere in the app) and fastapi-users
(installed in the dev venv but unused by any code)."
```

---

### Task 2: Write `.env.example`

**Files:**
- Create: `.env.example`

**Interfaces:**
- Consumes: nothing
- Produces: `.env.example` at repo root — Task 3's runbook references this file as the checklist of what to paste into Render's env-var UI

- [ ] **Step 1: List every env var `config.py` reads**

```bash
grep -n "os.getenv\|os.environ" config.py
```

Expected output (for reference — confirms the full set this step documents):
`FRONTEND_URL`, `BACKEND_PUBLIC_URL`, `CORS_ALLOWED_ORIGINS`,
`USDA_API_KEY`, `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`,
`DATABASE_URL`, `SECRET_KEY`, `ACCESS_TOKEN_EXPIRE_MINUTES`,
`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`.

- [ ] **Step 2: Write `.env.example`**

```
# Copy this file's variable NAMES into Render's environment-variable UI.
# Never commit real values — this file documents names only.

# ── Database ──────────────────────────────────
# Neon connection string, using the asyncpg driver scheme.
# Get this from the Neon dashboard after creating a project — it looks
# like: postgresql+asyncpg://<user>:<password>@<host>/<dbname>
DATABASE_URL=

# ── Auth ──────────────────────────────────────
# Generate with: python3 -c "import secrets; print(secrets.token_hex(32))"
# Must be a fresh value for production — never reuse a local-dev SECRET_KEY.
SECRET_KEY=
# Optional — defaults to 7 days (60 * 24 * 7 minutes) if unset.
ACCESS_TOKEN_EXPIRE_MINUTES=

# ── App URLs / CORS ───────────────────────────
# The Cloudflare Pages URL once it exists, e.g. https://pakupaku.pages.dev
FRONTEND_URL=
# The Render service's own public URL, e.g. https://pakupaku-api.onrender.com
BACKEND_PUBLIC_URL=
# Comma-separated list of origins allowed to call this API.
# Should include FRONTEND_URL; localhost:3000 is already allowed by
# config.py's default even if you don't list it here.
CORS_ALLOWED_ORIGINS=

# ── Email (SMTP) ──────────────────────────────
# Existing Gmail App Password already used for local dev — reused as-is,
# no new email infrastructure for this deployment.
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM=

# ── USDA ──────────────────────────────────────
USDA_API_KEY=

# ── LLM (recipe import fallback) ──────────────
# Optional — only needed if a blog page lacks schema.org/JSON-LD Recipe
# markup. Import returns a 503 for that fallback path when unset.
LLM_API_KEY=
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_MODEL=openai/gpt-oss-20b
```

- [ ] **Step 3: Verify every `config.py` env var is documented**

```bash
comm -23 \
  <(grep -oE 'os\.getenv\("[A-Z_]+"|os\.environ\["[A-Z_]+"' config.py | grep -oE '[A-Z_]+$' | sort -u) \
  <(grep -oE '^[A-Z_]+=' .env.example | tr -d '=' | sort -u)
```

Expected: empty output (every var `config.py` reads appears in
`.env.example`). If any names print, add them to `.env.example` and
re-run.

- [ ] **Step 4: Commit**

```bash
git add .env.example
git commit -m "Add .env.example documenting production environment variables

Lists every variable config.py reads, with guidance on where each value
comes from (Neon, a freshly generated SECRET_KEY, existing SMTP/USDA
credentials) — no real values, so this is safe to commit. Serves as the
checklist for what to paste into Render's env-var UI."
```

---

### Task 3: Write the deployment runbook

**Files:**
- Create: `docs/deployment.md`

**Interfaces:**
- Consumes: `requirements.txt` (Task 1), `.env.example` (Task 2) — the runbook references both by name
- Produces: `docs/deployment.md` — Task 4 is this document executed live

- [ ] **Step 1: Write `docs/deployment.md`**

```markdown
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
```

- [ ] **Step 2: Commit**

```bash
git add docs/deployment.md
git commit -m "Add step-by-step deployment runbook (Neon -> Render -> Cloudflare Pages)

Covers account creation and configuration on all three free-tier
services, in dependency order, plus a post-deploy verification
checklist. Surfaces one real gap found while writing it: the frontend's
fetch() calls rely on package.json's dev-only proxy field, which has no
effect in a production static build — flagged as a required small
follow-up rather than solved here, since this plan is infra/config
only."
```

---

### Task 4: Execute the runbook live with the user

**⚠️ NOT SUBAGENT-DELEGABLE.** This task requires the user's own
accounts, their own browser session, and their own credentials — a
subagent has no way to sign up for Render/Neon/Cloudflare Pages or
click through their dashboards on the user's behalf. Execute this task
in the main conversation, interactively, narrating each step and
waiting for the user to confirm what they see on screen before
proceeding to the next.

**Files:** none (this task produces deployed infrastructure, not repo changes) — except the `REACT_APP_API_URL` follow-up surfaced in Task 3, which should be scoped and confirmed with the user as its own small bounded change before Cloudflare Pages step 3 can be verified end-to-end.

**Interfaces:**
- Consumes: `docs/deployment.md` (Task 3) — this task *is* that document, executed
- Produces: a live, reachable PakuPaku deployment; no code artifacts

- [ ] **Step 1: Confirm the `REACT_APP_API_URL` gap with the user before starting**

Task 3 surfaced that Cloudflare Pages can't actually reach the Render
API without a small frontend code change (relative `fetch()` paths only
work via the dev-only `proxy` field). Before walking through
`docs/deployment.md`, tell the user this gap exists and ask whether to
fix it now (as its own small bounded change, brainstormed and approved
the normal way) or defer the Cloudflare Pages step until later. Don't
silently build around it.

- [ ] **Step 2: Walk through `docs/deployment.md` section 1 (Neon) with the user**

Narrate each substep from the runbook. Wait for the user to report the
rewritten `DATABASE_URL` value exists before moving on — don't ask them
to paste the actual value into chat (it contains a password); just
confirm they have it saved somewhere to paste into Render directly.

- [ ] **Step 3: Walk through section 2 (Render) with the user**

Generate the `SECRET_KEY` value yourself (`python3 -c "import secrets;
print(secrets.token_hex(32))"`) and give it to the user directly to
paste — per the spec, this is the one value the assistant hands over
directly rather than the user sourcing it themselves. Confirm the
deploy log reaches `Application startup complete` before moving on.

- [ ] **Step 4: Walk through section 3 (Cloudflare Pages) with the user**

Only after step 1's `REACT_APP_API_URL` gap has been explicitly
resolved (fixed or consciously deferred).

- [ ] **Step 5: Walk through section 4 (wire CORS back together) with the user**

- [ ] **Step 6: Walk through section 5 (verify) with the user**

Confirm each checklist item explicitly — don't mark this task done on
the user's say-so alone if something in the list wasn't actually
checked (e.g. don't skip the cold-start wait).

---

## Plan Self-Review

**Spec coverage:**
- Complete pinned `requirements.txt` → Task 1 ✓
- `.env.example` → Task 2 ✓
- Render start-command documentation → Task 3, runbook section 2 ✓
- Step-by-step runbook covering Neon → Render → Cloudflare Pages → Task 3 produces it, Task 4 executes it ✓
- User performs account creation/deploy actions; assistant walks through interactively → Task 4 ✓
- No `config.py` changes → confirmed nowhere in this plan touches it ✓
- Desktop-account unification and production migration tooling excluded → confirmed absent from all four tasks; the "Known gap" note in Task 3's runbook explicitly defers the migration-tool question rather than solving it ✓

**Gap found during planning, not in the original spec:** the frontend's
reliance on `package.json`'s dev-only `proxy` field means Cloudflare
Pages can't reach Render without a small code change. This wasn't
identified during brainstorming. Rather than silently expanding this
plan's scope to fix it, Task 3 documents it explicitly and Task 4 Step 1
requires surfacing it to the user as a decision point before proceeding
— consistent with the spec's boundary that this work is
infrastructure/config only, not application code changes.
