# Shared Recipe Library — Design

## Problem

Every recipe in PakuPaku today is strictly personal: `Recipe.user_id` is
non-nullable, and every recipe route (`GET/POST/PATCH/DELETE /recipes*`,
and the recipe-logging path in `POST /logs`) filters by
`Recipe.user_id == current_user.id`. There is no way for one user's
recipe to be visible to anyone else, and no admin concept anywhere in
the app (`User` has no role field at all).

This adds a shared recipe library: recipes an admin curates that every
user can browse, log directly, or copy into their own personal
collection. It also closes a real, separate gap found while designing
this — recipe-import (`recipe_import.py`) already extracts `image_url`
and `source_url` from a blog page, but both are **discarded** when the
draft is actually saved, because `Recipe` has no columns for them.
Fixing that benefits personal recipes too, not just shared ones.

## Goals / non-goals

- **Goal:** an admin-curated recipe library, browsable and usable by
  every user, structurally separate in intent from personal recipes but
  reusing the same underlying `Recipe`/`RecipeIngredient` tables and
  routes.
- **Goal:** every recipe (personal or shared) can carry an image, a
  source link, step-by-step instructions, and a set of diet tags —
  fields that exist today only as transient recipe-import artifacts (or
  not at all) and are never persisted.
- **Goal:** a user can act on a shared recipe two ways — log a serving
  directly to today's food diary, or save an independent personal copy.
- **Non-goal:** self-service admin promotion. One designated account
  (yours) gets `is_admin = true` via a one-off SQL command run directly
  against the database — no admin-management UI.
- **Non-goal:** a real multi-image gallery. One `image_url` per recipe,
  matching what URL-import already extracts (a single `og:image` /
  JSON-LD image).
- **Non-goal:** editing someone else's shared recipe in place. Users
  can only copy a shared recipe into their own collection and edit the
  copy; only the admin who owns a shared recipe can edit or delete the
  original.

## Data model

Two additive migrations, both nullable/defaulted so existing rows need
no backfill:

**`User`** gains one column:
```python
is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
```

**`Recipe`** gains five columns:
```python
image_url:    Mapped[Optional[str]]  = mapped_column(String(1000), nullable=True)
source_url:   Mapped[Optional[str]]  = mapped_column(String(1000), nullable=True)
instructions: Mapped[Optional[str]]  = mapped_column(Text, nullable=True)
diet_tags:    Mapped[Optional[str]]  = mapped_column(String(500), nullable=True)
is_shared:    Mapped[bool]           = mapped_column(Boolean, default=False, nullable=False)
```

`instructions` stores newline-separated steps as a single text block —
the same portability reasoning as everywhere else in this codebase that
needs a variable-length list in a column: Postgres has array types,
SQLite (the desktop build's driver) doesn't, and this app runs on both.
Rendered as an ordered list on the frontend by splitting on newlines.

`diet_tags` stores a comma-joined list of tag keys, identical in shape
to the existing `User.metabolic_conditions` column — reusing an
established storage pattern rather than introducing a new one. Unlike
`metabolic_conditions` (whose unknown keys are silently ignored by
`apply_metabolic_conditions()`, not rejected), `diet_tags` validates
against this fixed set with a Pydantic validator, rejecting anything
else with a 422 — the whole point of a tag set is that "browse vegan
recipes" means something consistent:

```
vegan, vegetarian, pescatarian, flexitarian,
gluten_free, dairy_free, nut_free, soy_free, egg_free, shellfish_free,
keto, low_carb, paleo, whole30, low_fodmap, diabetic_friendly,
low_sodium, low_fat, high_protein,
halal, kosher,
mediterranean, dash
```

## Backend routes

- **`POST /recipes` / `PATCH /recipes/{id}`** — `RecipeCreateRequest`/
  `RecipeUpdateRequest` gain `image_url`, `source_url`, `instructions`,
  `diet_tags: List[str]`, and `is_shared: bool` (all optional).
  `is_shared` is accepted from any client but **the handler always
  overwrites it to `False` unless `current_user.is_admin` is true** —
  the request body's claim is never trusted on its own.
- **`GET /recipes/shared`** (new) — every `Recipe` row with
  `is_shared = True`, for any authenticated user, not filtered by
  `user_id`.
- **`POST /recipes/{id}/copy`** (new) — looks up the recipe by id where
  `user_id == current_user.id OR is_shared == True` (404 otherwise),
  then inserts a new `Recipe` + `RecipeIngredient` set owned by
  `current_user`, `is_shared = False`. Returns the new `RecipeResponse`.
- **`POST /logs`** — the existing recipe-ownership check
  (`Recipe.user_id == current_user.id`) becomes
  `(Recipe.user_id == current_user.id) | (Recipe.is_shared == True)`,
  so a user can log a shared recipe they don't own.
- **`recipe_import.py`** — `build_import_draft()` already returns
  `image_url`/`source_url` on `RecipeImportDraft`; the frontend's save
  step now forwards them into `RecipeCreateRequest` instead of dropping
  them. `instructions` extraction is new: `extract_structured_recipe()`
  reads schema.org JSON-LD's `recipeInstructions` field (present in the
  markup today, just never read); `extract_recipe_via_llm()`'s prompt
  gains one line asking the model to include a `steps` array in its
  JSON response, joined with newlines into the same `instructions`
  shape either path produces.

## Frontend

- **`RecipeBuilder.tsx`** create/edit form: new fields for `image_url`
  (text input), `source_url` (text input), `instructions` (textarea,
  one step per line), and a `diet_tags` checkbox group — all visible to
  every user. An `is_shared` checkbox appears only when
  `userProfile.is_admin` is true.
- **New "Browse Shared Recipes" section**, listing `GET /recipes/shared`
  results with image, diet tags, and two actions: **Log now** (reuses
  the existing quantity/meal-category picker already used for logging a
  personal saved recipe) and **Save a copy** (`POST /recipes/{id}/copy`).
- Any detailed recipe view (personal saved recipes, the shared browser)
  now renders the image, diet tags, instructions as a numbered list, and
  a "View original" link when `source_url` is set.

## Testing

- **Backend:**
  - `GET /recipes/shared` returns only `is_shared=True` rows, for a
    user who owns none of them.
  - `POST /recipes` from a non-admin with `is_shared: true` in the body
    still creates the recipe with `is_shared = False`.
  - `POST /recipes/{id}/copy` on a shared recipe produces an
    independent row (editing the copy doesn't touch the original).
  - `POST /recipes/{id}/copy` on a recipe that's neither yours nor
    shared returns 404.
  - `POST /logs` with a shared recipe's id, from a user who doesn't own
    it, succeeds.
  - `POST /logs` with a *personal, unshared* recipe id belonging to
    someone else still 404s (the relaxation is additive, not a
    blanket bypass).
  - A recipe imported from a URL with schema.org `recipeInstructions`
    markup persists non-null `instructions` after save (verifies the
    "captured but discarded" gap is actually closed, not just the new
    columns existing).
- **Frontend:** the `is_shared` checkbox is absent for a non-admin
  `userProfile`; browse → log and browse → copy both work end to end
  against a real backend, not mocks — consistent with how every other
  feature this session was verified.
