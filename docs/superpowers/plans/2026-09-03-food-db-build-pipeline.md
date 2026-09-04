# Multi-Country Food Database — Build Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an offline pipeline that merges national food-composition tables into one averaged generic-food artifact, `data/foods.sqlite`, committed to the repo.

**Architecture:** A `scripts/build_food_db/` package. Per-source extractors convert raw downloads into a common `NormalisedRow`. A normaliser derives a canonical key + preparation state per row. A matcher groups rows across sources (exact key, then `rapidfuzz` fuzzy) and writes disagreements to a review CSV whose resolutions are committed. An aggregator applies a per-nutrient sanity filter and takes the median (mean when only two sources) across surviving sources. A portions step name-matches USDA FNDDS household measures onto each food. `build.py` orchestrates and writes the SQLite artifact.

**Tech Stack:** Python 3.8 (repo floor — `typing.Optional`/`typing.List`, no `X | None`), `rapidfuzz` for fuzzy matching, `openpyxl` for xlsx sources, stdlib `sqlite3` and `csv`, `pytest` with `asyncio_mode = auto`.

**Spec:** `docs/superpowers/specs/2026-09-03-multi-country-food-database-design.md`

## Status

Tasks 1–8 are **implemented and reviewed** on branch `food-db-spec` (at the
final fix-wave commit). Task 9 (acquire the real datasets, resolve conflicts,
commit `data/foods.sqlite`) is **not started** — it needs the user to download
the six source datasets first.

## Corrections applied during implementation

Where this plan and the code as built disagree, the code is authoritative:

- `to_mcg(0.001)` is `1000.0`, not `1.0` — Task 4 Step 2's sample assertion
  used mg, but `to_mcg` returns micrograms.
- `canonical_key("Water, tap, drinking")` is **not** `"water"` (Task 4 Step 7's
  sample assertion); after F12 it normalises to `"drinking tap water"`.
- `rapidfuzz==3.9.7`, not `3.10.1` — rapidfuzz 3.10.x requires Python 3.9 and
  the repo floor is 3.8.
- Task 8's INSERT placeholder count is `8 + len(NUTRIENT_FIELDS)`, not
  `7 + …` — there are 8 non-nutrient columns (id, canonical_name, aliases,
  category, prep_state, portions, source_ids, source_count).
- `main()` gained `os.makedirs` for the `review/` and output directories, plus
  `root` / `out_path` parameters so a test can drive the pipeline end-to-end.

Final-review fix wave (F1–F13):

- **F1** — `main()` hands each extractor `raw/<source_id>/`, not the `raw/`
  root; two `main()` tests added.
- **F2** — the CoFID extractor reads its `.xlsx` workbook via `read_xlsx_rows`
  + a pinned `SHEET`, like the other xlsx sources.
- **F3** — `scripts/build_food_db/review/conflicts.csv` is git-ignored.
- **F4** — `load_fndds_portions` divides `gram_weight` by `amount`, and
  restricts portion-name rows to `foundation_food` / `sr_legacy_food` /
  `survey_fndds_food`; no separate FNDDS release is read (portions come from
  `raw/usda/food_portion.csv` in the Full Download).
- **F5** — a nutrient is emitted only with **≥ 2 distinct sources**
  (per-source mean taken first); the mini fixture gained a real second source.
- **F6** — nutrient-agreement tolerance split into `MACRO_TOLERANCE` (0.25) /
  `MICRO_TOLERANCE` (0.60); spread is compared to the median.
- **F7** — `group_foods` runs once: `build()` takes an optional `groups=` and
  `main()` passes the groups it already built.
- **F8** — every extractor passes `category=None` (raw source category columns
  are an incoherent mix; a shared vocabulary is Plan-2 work).
- **F9** — `parse_float` treats a comma as a decimal separator only when there
  is exactly one with ≤ 2 trailing digits, else strips it as a thousands
  separator (`"1,200"` → `1200.0`).
- **F10** — the artifact is written to `<out>.tmp` then `os.replace`d into
  place, so a mid-build crash never destroys a committed artifact.
- **F11** — `PRAGMA page_size = 4096` before `CREATE TABLE`, for
  cross-machine determinism.
- **F12** — `canonical_key` keeps a stopword in head-noun position
  (`"coconut water"` stays `"coconut water"`) and falls back to the full
  sorted token list when every token is a stopword.
- **F13** — dropped unused `dataclasses.field` / `fields` imports from
  `model.py`; annotated `read_xlsx_rows(path: str, sheet: Optional[str] = None)`.

## Global Constraints

- Python 3.8 syntax only — `typing.Optional[X]` / `typing.List[X]`, never `X | None` or `list[X]` in annotations.
- New third-party deps go in `requirements.txt`, pinned to an exact version, with a one-line comment.
- Raw source data files are **never committed**. They live under `scripts/build_food_db/raw/` which is git-ignored. `scripts/build_food_db/README.md` documents where to download each.
- The only committed build output is `data/foods.sqlite`. Regenerating it from the same raw inputs + `review/decisions.csv` + `translations/` must be byte-identical (deterministic): sort every collection before writing, no timestamps in the artifact.
- Nutrient field names match `usda.py::extract_nutrients` exactly: `calories_per_100g`, `protein_per_100g`, `fat_per_100g`, `carbs_per_100g`, `fiber_per_100g`, `sugar_per_100g`, `sodium_mg_per_100g`, `calcium_mg_per_100g`, `iron_mg_per_100g`, `vitamin_c_mg_per_100g`, `vitamin_d_mcg_per_100g`, `vitamin_b12_mcg_per_100g`. (Spec uses shorthand; this list is authoritative for column names in the artifact.)
- Sanity-filter thresholds (spec §"Sanity filter"): `calories_per_100g` must be `0 <= x <= 900`; each macro `>= 0`; `protein + fat + carbs + fiber <= 105` (g/100g). These are the starting values — keep them as named module constants so they are easy to tune.
- Fuzzy-match thresholds (spec §"Cross-source food identity"): auto-merge when `rapidfuzz.fuzz.token_set_ratio >= 92`; nutrient agreement tolerance for auto-accept is `±25%` relative (with a `0.5` absolute floor so trace nutrients near zero don't trip it). Named constants.
- A food is emitted only if, after the sanity filter, **at least one nutrient has ≥ 2 surviving source values**. Per nutrient: median when ≥ 3 sources, mean when exactly 2, `None` when < 2.
- Tests live under `tests/build_food_db/`. Run with `python -m pytest tests/build_food_db/ -v`.

---

## File Structure

**Create:**

- `scripts/build_food_db/__init__.py` — empty, makes the package importable from tests.
- `scripts/build_food_db/README.md` — per-source download instructions, licence notes, run instructions.
- `scripts/build_food_db/model.py` — `NormalisedRow` dataclass + `NUTRIENT_FIELDS` tuple, the shared contract every stage passes around.
- `scripts/build_food_db/normalise.py` — `canonical_key(name)`, `parse_prep_state(name)`, `normalise_row(row)`.
- `scripts/build_food_db/sources/__init__.py` — `ALL_SOURCES` registry.
- `scripts/build_food_db/sources/base.py` — `Source` protocol + `load_csv`/`load_xlsx` helpers + unit-conversion helpers.
- `scripts/build_food_db/sources/usda.py` — reference extractor (FDC CSV export).
- `scripts/build_food_db/sources/cofid.py`, `ciqual.py`, `afcd.py`, `cnf.py`, `frida.py` — one extractor each, same shape as `usda.py`.
- `scripts/build_food_db/sources/fao_regional.py`, `korea.py` — added only if their licence clears (Task 1); skipped otherwise.
- `scripts/build_food_db/match.py` — `group_foods(rows)` → merge groups + `write_conflicts(...)`, `load_decisions(...)`.
- `scripts/build_food_db/aggregate.py` — `sanity_filter(values, field)`, `aggregate_group(group)` → `AggregatedFood`.
- `scripts/build_food_db/portions.py` — `load_fndds_portions(raw_dir)`, `attach_portions(foods, portions)`.
- `scripts/build_food_db/build.py` — `main()`; wires the stages, writes `data/foods.sqlite`.
- `scripts/build_food_db/review/decisions.csv` — committed; starts with just a header.
- `scripts/build_food_db/translations/korea_en.csv` — committed; created in Task 1 (may stay header-only if Korea is dropped).
- `docs/food-data-sources.md` — the licence + attribution register.
- `tests/build_food_db/__init__.py`
- `tests/build_food_db/conftest.py` — fixture-slice paths.
- `tests/build_food_db/fixtures/` — tiny committed CSV slices per source (~10 rows each) + a fake FNDDS portions slice.
- `tests/build_food_db/test_normalise.py`, `test_sources.py`, `test_match.py`, `test_aggregate.py`, `test_portions.py`, `test_build_golden.py`.

**Modify:**

- `requirements.txt` — add `rapidfuzz`, `openpyxl`.
- `.gitignore` — add `scripts/build_food_db/raw/`.

**This plan does NOT touch:** `main.py`, `recipe_import.py`, `usda.py`, `schemas.py`, `config.py`, `create_tables.py`, or any frontend file. Those are the second plan (runtime cutover).

---

## Task 1: Licence verification & source register

**Files:**
- Create: `docs/food-data-sources.md`
- Create: `scripts/build_food_db/README.md`
- Create: `scripts/build_food_db/translations/korea_en.csv` (header only)
- Create: `scripts/build_food_db/review/decisions.csv` (header only)
- Modify: `.gitignore`

**Interfaces:**
- Produces: the definitive list of `ALL_SOURCES` members for Task 4 — each confirmed source's id string, homepage, licence name, attribution string, and raw-file layout notes.

This task is research + documentation. No code, no tests. Its deliverable is a filled-in `docs/food-data-sources.md` that every later task treats as the source of truth for which extractors to write.

- [x] **Step 1: Create the git-ignore entry**

Append to `.gitignore`:

```
# Raw national food-composition downloads for the food-DB build pipeline.
scripts/build_food_db/raw/
```

- [x] **Step 2: Confirm the six known-open sources**

For each of USDA FDC, CoFID (UK), CIQUAL (France), AFCD (Australia/FSANZ), CNF (Canada), Frida (Denmark): record in `docs/food-data-sources.md` a row with — source id (`usda`, `cofid`, `ciqual`, `afcd`, `cnf`, `frida`), dataset name + edition/year, download URL, licence name + URL, the verbatim attribution string the licence requires, and the file format (CSV / xlsx / multi-file release).

- [x] **Step 3: Resolve the four pending licences**

For each of FAO West Africa, FAO Central/East Africa, FAO ASEAN, and Korea (RDA / data.go.kr): find the dataset's licence page. If it permits redistribution **and** commercial use (reject CC BY-NC, CC BY-NC-SA, "research only", "no redistribution"), add it as a confirmed row exactly like Step 2 and note `included: yes`. Otherwise add the row with `included: no — <reason>` and do not write an extractor for it later. Record the decision date.

- [x] **Step 4: Write `scripts/build_food_db/README.md`**

Contents: the list of confirmed sources; for each, the exact download steps and where the file(s) go under `scripts/build_food_db/raw/<source_id>/`; which sub-files are needed from multi-file releases (USDA FDC: `food.csv`, `food_nutrient.csv`, `nutrient.csv`, plus FNDDS `fndds_ingredient_nutrient_value` / portion files — name them precisely once the release is downloaded); and the run command `python -m scripts.build_food_db.build`.

- [x] **Step 5: Create the committed stubs**

`scripts/build_food_db/review/decisions.csv` with header:

```csv
group_id,decision,canonical_name,note
```

`scripts/build_food_db/translations/korea_en.csv` with header:

```csv
korean_name,english_name
```

- [x] **Step 6: Commit**

```bash
git add .gitignore docs/food-data-sources.md scripts/build_food_db/README.md scripts/build_food_db/review/decisions.csv scripts/build_food_db/translations/korea_en.csv
git commit -m "docs: food-DB build pipeline source register and licence decisions"
```

---

## Task 2: Shared data model

**Files:**
- Create: `scripts/build_food_db/__init__.py` (empty)
- Create: `scripts/build_food_db/model.py`
- Create: `tests/build_food_db/__init__.py` (empty)
- Test: `tests/build_food_db/test_model.py`

**Interfaces:**
- Produces:
  - `NUTRIENT_FIELDS: Tuple[str, ...]` — the 12 nutrient column names from Global Constraints, in a fixed order.
  - `NormalisedRow` dataclass: `source_id: str`, `source_food_id: str`, `name: str`, `canonical_key: str` (filled by Task 3, `""` until then), `prep_state: str` (same), `category: Optional[str]`, plus one `Optional[float]` field per name in `NUTRIENT_FIELDS`.
  - `NormalisedRow.nutrients() -> Dict[str, Optional[float]]` — the 12 nutrient fields as a dict.

- [x] **Step 1: Write the failing test**

```python
# tests/build_food_db/test_model.py
from scripts.build_food_db.model import NUTRIENT_FIELDS, NormalisedRow


def test_nutrient_fields_are_the_twelve_extract_nutrients_columns():
    assert NUTRIENT_FIELDS == (
        "calories_per_100g", "protein_per_100g", "fat_per_100g",
        "carbs_per_100g", "fiber_per_100g", "sugar_per_100g",
        "sodium_mg_per_100g", "calcium_mg_per_100g", "iron_mg_per_100g",
        "vitamin_c_mg_per_100g", "vitamin_d_mcg_per_100g", "vitamin_b12_mcg_per_100g",
    )


def test_normalised_row_nutrients_returns_all_twelve_keys():
    row = NormalisedRow(
        source_id="usda", source_food_id="123", name="Broccoli, raw",
        canonical_key="", prep_state="", category="vegetable",
        calories_per_100g=34.0, protein_per_100g=2.8,
    )
    n = row.nutrients()
    assert set(n) == set(NUTRIENT_FIELDS)
    assert n["calories_per_100g"] == 34.0
    assert n["fiber_per_100g"] is None
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/build_food_db/test_model.py -v`
Expected: FAIL — `ModuleNotFoundError: scripts.build_food_db.model`

- [x] **Step 3: Write minimal implementation**

```python
# scripts/build_food_db/model.py
from dataclasses import dataclass, field, fields
from typing import Dict, Optional, Tuple

NUTRIENT_FIELDS: Tuple[str, ...] = (
    "calories_per_100g", "protein_per_100g", "fat_per_100g",
    "carbs_per_100g", "fiber_per_100g", "sugar_per_100g",
    "sodium_mg_per_100g", "calcium_mg_per_100g", "iron_mg_per_100g",
    "vitamin_c_mg_per_100g", "vitamin_d_mcg_per_100g", "vitamin_b12_mcg_per_100g",
)


@dataclass
class NormalisedRow:
    source_id: str
    source_food_id: str
    name: str
    canonical_key: str = ""
    prep_state: str = ""
    category: Optional[str] = None
    calories_per_100g: Optional[float] = None
    protein_per_100g: Optional[float] = None
    fat_per_100g: Optional[float] = None
    carbs_per_100g: Optional[float] = None
    fiber_per_100g: Optional[float] = None
    sugar_per_100g: Optional[float] = None
    sodium_mg_per_100g: Optional[float] = None
    calcium_mg_per_100g: Optional[float] = None
    iron_mg_per_100g: Optional[float] = None
    vitamin_c_mg_per_100g: Optional[float] = None
    vitamin_d_mcg_per_100g: Optional[float] = None
    vitamin_b12_mcg_per_100g: Optional[float] = None

    def nutrients(self) -> Dict[str, Optional[float]]:
        return {name: getattr(self, name) for name in NUTRIENT_FIELDS}
```

- [x] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/build_food_db/test_model.py -v`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add scripts/build_food_db/__init__.py scripts/build_food_db/model.py tests/build_food_db/__init__.py tests/build_food_db/test_model.py
git commit -m "feat: NormalisedRow model for food-DB build pipeline"
```

---

## Task 3: Name normalisation

**Files:**
- Create: `scripts/build_food_db/normalise.py`
- Test: `tests/build_food_db/test_normalise.py`

**Interfaces:**
- Consumes: `NormalisedRow` from Task 2.
- Produces:
  - `PREP_STATES: Tuple[str, ...]` = `("raw", "cooked", "dried", "unspecified")`.
  - `parse_prep_state(name: str) -> str` — one of `PREP_STATES`.
  - `canonical_key(name: str) -> str` — lowercased, punctuation stripped, tokens sorted, prep-state words removed, whitespace-collapsed.
  - `normalise_row(row: NormalisedRow) -> NormalisedRow` — returns the same row with `canonical_key` and `prep_state` set.

- [x] **Step 1: Write the failing test**

```python
# tests/build_food_db/test_normalise.py
from scripts.build_food_db.model import NormalisedRow
from scripts.build_food_db.normalise import (
    canonical_key, parse_prep_state, normalise_row,
)


def test_prep_state_detection():
    assert parse_prep_state("Potato, raw") == "raw"
    assert parse_prep_state("Potato, boiled, drained") == "cooked"
    assert parse_prep_state("Potato, baked") == "cooked"
    assert parse_prep_state("Apricot, dried") == "dried"
    assert parse_prep_state("Olive oil") == "unspecified"


def test_canonical_key_is_order_and_punctuation_insensitive():
    assert canonical_key("Broccoli, raw") == canonical_key("raw broccoli")
    assert canonical_key("Rice, white, long-grain") == canonical_key("long grain white rice")


def test_canonical_key_drops_prep_words():
    # prep state is tracked separately, not part of the key
    assert canonical_key("Potato, raw") == canonical_key("Potato, boiled")
    assert canonical_key("Potato") == "potato"


def test_normalise_row_populates_both_fields():
    row = NormalisedRow(source_id="cofid", source_food_id="12-345",
                        name="Carrots, boiled in unsalted water")
    out = normalise_row(row)
    assert out.prep_state == "cooked"
    assert out.canonical_key == canonical_key("carrots")
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/build_food_db/test_normalise.py -v`
Expected: FAIL — `ModuleNotFoundError: scripts.build_food_db.normalise`

- [x] **Step 3: Write minimal implementation**

```python
# scripts/build_food_db/normalise.py
import re
from typing import Tuple

from scripts.build_food_db.model import NormalisedRow

PREP_STATES: Tuple[str, ...] = ("raw", "cooked", "dried", "unspecified")

_COOKED_WORDS = {
    "cooked", "boiled", "baked", "roasted", "fried", "grilled", "steamed",
    "braised", "stewed", "simmered", "sauteed", "microwaved", "poached",
}
_RAW_WORDS = {"raw", "fresh", "uncooked"}
_DRIED_WORDS = {"dried", "dehydrated", "sun-dried"}
# words removed from the canonical key (prep + filler that doesn't identify the food)
_KEY_STOPWORDS = (
    _COOKED_WORDS | _RAW_WORDS | _DRIED_WORDS
    | {"in", "with", "without", "and", "of", "unsalted", "salted", "water",
       "drained", "added", "no"}
)
_PUNCT = re.compile(r"[^a-z0-9\s]")
_WS = re.compile(r"\s+")


def parse_prep_state(name: str) -> str:
    tokens = set(_WS.sub(" ", _PUNCT.sub(" ", name.lower())).split())
    if tokens & _DRIED_WORDS:
        return "dried"
    if tokens & _COOKED_WORDS:
        return "cooked"
    if tokens & _RAW_WORDS:
        return "raw"
    return "unspecified"


def canonical_key(name: str) -> str:
    cleaned = _WS.sub(" ", _PUNCT.sub(" ", name.lower())).strip()
    tokens = [t for t in cleaned.split() if t and t not in _KEY_STOPWORDS]
    return " ".join(sorted(tokens))


def normalise_row(row: NormalisedRow) -> NormalisedRow:
    row.prep_state = parse_prep_state(row.name)
    row.canonical_key = canonical_key(row.name)
    return row
```

- [x] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/build_food_db/test_normalise.py -v`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add scripts/build_food_db/normalise.py tests/build_food_db/test_normalise.py
git commit -m "feat: canonical-key and prep-state normalisation for food-DB build"
```

---

## Task 4: Source extractors

**Files:**
- Create: `scripts/build_food_db/sources/__init__.py`
- Create: `scripts/build_food_db/sources/base.py`
- Create: `scripts/build_food_db/sources/usda.py`
- Create: `scripts/build_food_db/sources/cofid.py`, `ciqual.py`, `afcd.py`, `cnf.py`, `frida.py`
- Create (only if Task 1 confirmed them): `scripts/build_food_db/sources/fao_regional.py`, `korea.py`
- Modify: `requirements.txt` (add `openpyxl`)
- Create: `tests/build_food_db/conftest.py`
- Create: `tests/build_food_db/fixtures/<source_id>_slice.csv` (one per confirmed source, ~10 rows)
- Test: `tests/build_food_db/test_sources.py`

**Interfaces:**
- Consumes: `NormalisedRow` (Task 2), `normalise_row` (Task 3).
- Produces:
  - `scripts/build_food_db/sources/base.py`:
    - `Source` — object with `id: str` and `extract(raw_dir: str) -> List[NormalisedRow]`.
    - `to_mg(value_g)`, `to_mcg(value_g)`, `kj_to_kcal(value_kj)` — unit helpers returning `Optional[float]`.
    - `read_csv_rows(path, delimiter=",", encoding="utf-8") -> Iterator[Dict[str, str]]`.
  - `scripts/build_food_db/sources/__init__.py`: `ALL_SOURCES: List[Source]` — every confirmed extractor instance.
  - Each `sources/<id>.py`: a module-level `SOURCE` instance whose `extract()` returns rows with `source_id`, `source_food_id`, `name`, `category`, and whatever nutrient fields the source provides (converted to per-100g, mg/mcg per the field names), then run through `normalise_row`.

**Note for the implementer:** the exact column names for each non-USDA source are only knowable once the raw file is in `scripts/build_food_db/raw/<id>/`. Write each extractor against a committed ~10-row fixture slice that mirrors the real file's header; when the real download is present, adjust the column-name constants at the top of the module. USDA FDC's CSV schema (`food.csv`, `food_nutrient.csv`, `nutrient.csv`) is stable and documented — do it fully first as the reference.

- [x] **Step 1: Add `openpyxl` to requirements**

Append to `requirements.txt`:

```
openpyxl==3.1.5  # read .xlsx national food-composition tables in the build pipeline
```

Run: `pip install -r requirements.txt`

- [x] **Step 2: Write the failing test for `base.py` helpers**

```python
# tests/build_food_db/test_sources.py
from scripts.build_food_db.sources.base import to_mg, to_mcg, kj_to_kcal


def test_unit_helpers():
    assert to_mg(0.5) == 500.0          # 0.5 g -> mg
    assert to_mcg(0.001) == 1.0         # 0.001 g -> mcg
    assert round(kj_to_kcal(1000.0), 1) == 239.0
    assert to_mg(None) is None
```

- [x] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/build_food_db/test_sources.py -v`
Expected: FAIL — `ModuleNotFoundError: scripts.build_food_db.sources.base`

- [x] **Step 4: Implement `base.py`**

```python
# scripts/build_food_db/sources/base.py
import csv
from typing import Dict, Iterator, List, Optional

from scripts.build_food_db.model import NormalisedRow


class Source:
    id = ""

    def extract(self, raw_dir: str) -> List[NormalisedRow]:
        raise NotImplementedError


def to_mg(value_g: Optional[float]) -> Optional[float]:
    return None if value_g is None else round(value_g * 1000.0, 4)


def to_mcg(value_g: Optional[float]) -> Optional[float]:
    return None if value_g is None else round(value_g * 1_000_000.0, 4)


def kj_to_kcal(value_kj: Optional[float]) -> Optional[float]:
    return None if value_kj is None else round(value_kj / 4.184, 4)


def read_csv_rows(path: str, delimiter: str = ",",
                  encoding: str = "utf-8") -> Iterator[Dict[str, str]]:
    with open(path, newline="", encoding=encoding) as fh:
        yield from csv.DictReader(fh, delimiter=delimiter)


def parse_float(raw: Optional[str]) -> Optional[float]:
    if raw is None:
        return None
    text = raw.strip().replace(",", ".")
    if text in ("", "-", "N", "Tr", "tr", "trace", "[N]"):
        return None
    try:
        return float(text)
    except ValueError:
        return None
```

- [x] **Step 5: Run helper test to verify it passes**

Run: `python -m pytest tests/build_food_db/test_sources.py -v`
Expected: PASS

- [x] **Step 6: Add the USDA fixture slice**

Create `tests/build_food_db/fixtures/usda_food_slice.csv`, `usda_food_nutrient_slice.csv`, `usda_nutrient_slice.csv` — ~10 `food` rows (a mix of `data_type` = `foundation_food` / `sr_legacy_food`, **excluding** `branded_food` and `survey_fndds_food`), their matching `food_nutrient` rows for nutrient ids 1008/1003/1004/1005/1079/2000/1093/1087/1089/1162/1110/1178, and the `nutrient` lookup rows. Keep names recognisable: "Broccoli, raw", "Water, tap, drinking", "Potatoes, flesh and skin, raw".

- [x] **Step 7: Write the failing test for the USDA extractor**

```python
# add to tests/build_food_db/test_sources.py
import os
from scripts.build_food_db.sources.usda import SOURCE as USDA

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def test_usda_extractor_reads_generic_rows_only(tmp_path):
    # conftest copies the *_slice.csv files into tmp_path/usda/ under the
    # real release names; see conftest.usda_raw_dir
    from tests.build_food_db.conftest import usda_raw_dir
    raw = usda_raw_dir(tmp_path)

    rows = USDA.extract(raw)

    by_name = {r.name: r for r in rows}
    assert "Water, tap, drinking" in by_name
    water = by_name["Water, tap, drinking"]
    assert water.source_id == "usda"
    assert water.calories_per_100g == 0.0
    assert water.canonical_key == "water"          # normalise_row already applied
    # branded / FNDDS rows from the slice are excluded
    assert all("BRANDED" not in r.name.upper() for r in rows)
```

- [x] **Step 8: Run it to verify it fails**

Run: `python -m pytest tests/build_food_db/test_sources.py::test_usda_extractor_reads_generic_rows_only -v`
Expected: FAIL — `ModuleNotFoundError: scripts.build_food_db.sources.usda`

- [x] **Step 9: Write `conftest.py` + the USDA extractor**

```python
# tests/build_food_db/conftest.py
import os
import shutil

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def usda_raw_dir(tmp_path):
    d = tmp_path / "usda"
    d.mkdir()
    shutil.copy(os.path.join(FIX, "usda_food_slice.csv"), d / "food.csv")
    shutil.copy(os.path.join(FIX, "usda_food_nutrient_slice.csv"), d / "food_nutrient.csv")
    shutil.copy(os.path.join(FIX, "usda_nutrient_slice.csv"), d / "nutrient.csv")
    return str(d)
```

```python
# scripts/build_food_db/sources/usda.py
import os
from typing import Dict, List

from scripts.build_food_db.model import NormalisedRow
from scripts.build_food_db.normalise import normalise_row
from scripts.build_food_db.sources.base import Source, read_csv_rows, parse_float, to_mg, to_mcg

# USDA nutrient id -> NormalisedRow field. mg/mcg fields converted from the
# g-basis the CSV reports? No: food_nutrient.amount is already in the
# nutrient's own unit (mg for 1093/1087/1089/1162, ug for 1110/1178), so
# only assign directly.
_NUTRIENT_MAP = {
    "1008": ("calories_per_100g", 1.0),
    "1003": ("protein_per_100g", 1.0),
    "1004": ("fat_per_100g", 1.0),
    "1005": ("carbs_per_100g", 1.0),
    "1079": ("fiber_per_100g", 1.0),
    "2000": ("sugar_per_100g", 1.0),
    "1093": ("sodium_mg_per_100g", 1.0),
    "1087": ("calcium_mg_per_100g", 1.0),
    "1089": ("iron_mg_per_100g", 1.0),
    "1162": ("vitamin_c_mg_per_100g", 1.0),
    "1110": ("vitamin_d_mcg_per_100g", 1.0),
    "1178": ("vitamin_b12_mcg_per_100g", 1.0),
}
_GENERIC_TYPES = {"foundation_food", "sr_legacy_food"}


class _Usda(Source):
    id = "usda"

    def extract(self, raw_dir: str) -> List[NormalisedRow]:
        foods = {
            r["fdc_id"]: r
            for r in read_csv_rows(os.path.join(raw_dir, "food.csv"))
            if r.get("data_type") in _GENERIC_TYPES
        }
        rows: Dict[str, NormalisedRow] = {}
        for fdc_id, f in foods.items():
            rows[fdc_id] = NormalisedRow(
                source_id="usda", source_food_id=fdc_id,
                name=f["description"].strip(),
                category=(f.get("food_category_id") or None),
            )
        for fn in read_csv_rows(os.path.join(raw_dir, "food_nutrient.csv")):
            fid = fn["fdc_id"]
            if fid not in rows:
                continue
            mapping = _NUTRIENT_MAP.get(fn["nutrient_id"])
            if not mapping:
                continue
            field, factor = mapping
            val = parse_float(fn.get("amount"))
            if val is not None:
                setattr(rows[fid], field, round(val * factor, 4))
        return [normalise_row(r) for r in rows.values()]


SOURCE = _Usda()
```

- [x] **Step 10: Run the USDA test to verify it passes**

Run: `python -m pytest tests/build_food_db/test_sources.py -v`
Expected: PASS

- [x] **Step 11: Commit the reference extractor**

```bash
git add requirements.txt scripts/build_food_db/sources/ tests/build_food_db/conftest.py tests/build_food_db/fixtures/usda_*_slice.csv tests/build_food_db/test_sources.py
git commit -m "feat: USDA reference extractor + source base helpers"
```

- [x] **Step 12: Repeat Steps 6–11 for each remaining confirmed source**

For each of `cofid`, `ciqual`, `afcd`, `cnf`, `frida` (and `fao_regional`, `korea` if Task 1 confirmed them): add a ~10-row fixture slice mirroring that file's real header; write a failing test asserting one recognisable row extracts with the right `calories_per_100g` and `canonical_key`; implement `sources/<id>.py` with a module-top `COLS = {...}` column-name map and unit conversions (`kj_to_kcal` for kJ energy columns; `to_mg`/`to_mcg` where the source reports a nutrient in g); end each with `normalise_row`; add its `SOURCE` to `ALL_SOURCES` in `sources/__init__.py`; run; commit as `feat: <id> food-composition extractor`.

`ciqual` and `afcd` ship xlsx — add an `read_xlsx_rows(path, sheet)` helper to `base.py` (using `openpyxl`, `read_only=True`) the first time it's needed, with its own helper test.

- [x] **Step 13: Final commit for the sources package**

```bash
git add scripts/build_food_db/sources/__init__.py
git commit -m "feat: register all confirmed food-composition sources"
```

---

## Task 5: Cross-source matching & conflict review

**Files:**
- Create: `scripts/build_food_db/match.py`
- Test: `tests/build_food_db/test_match.py`

**Interfaces:**
- Consumes: `NormalisedRow` (Task 2), `NUTRIENT_FIELDS` (Task 2). `rapidfuzz` (already a dep — add if not: `rapidfuzz==3.10.1  # fuzzy food-name matching, build pipeline + runtime index`).
- Produces:
  - `TOKEN_SET_THRESHOLD = 92`, `NUTRIENT_TOLERANCE = 0.25`, `NUTRIENT_ABS_FLOOR = 0.5` — module constants.
  - `group_foods(rows: List[NormalisedRow]) -> List[MergeGroup]` — `MergeGroup` is a dataclass `group_id: str`, `canonical_name: str`, `rows: List[NormalisedRow]`, `auto_accepted: bool`. Rows with identical `(canonical_key, prep_state)` always group. Near-identical keys (`token_set_ratio >= TOKEN_SET_THRESHOLD`, same `prep_state`) are candidate-merged; the group is `auto_accepted=True` only if every shared nutrient agrees within tolerance, else `False`.
  - `write_conflicts(groups, path)` — write every `auto_accepted=False` group to a CSV: `group_id,source_id,name,<12 nutrient columns>` plus a blank `decision` column.
  - `load_decisions(path) -> Dict[str, str]` — `group_id -> decision` (`merge` / `separate` / `rename:<name>`), skipping blank rows.
  - `apply_decisions(groups, decisions) -> List[MergeGroup]` — split `separate` groups into singletons, apply `rename`, keep `merge`; raise `ValueError` listing any `auto_accepted=False` group with no decision.

- [x] **Step 1: Write the failing test**

```python
# tests/build_food_db/test_match.py
import pytest
from scripts.build_food_db.model import NormalisedRow
from scripts.build_food_db.normalise import normalise_row
from scripts.build_food_db.match import (
    group_foods, apply_decisions, load_decisions, write_conflicts,
)


def _row(src, name, **nut):
    return normalise_row(NormalisedRow(source_id=src, source_food_id=src + "1", name=name, **nut))


def test_identical_keys_group_and_auto_accept_when_nutrients_agree():
    rows = [
        _row("usda", "Broccoli, raw", calories_per_100g=34.0),
        _row("cofid", "raw broccoli", calories_per_100g=33.0),
    ]
    groups = group_foods(rows)
    assert len(groups) == 1
    assert groups[0].auto_accepted is True
    assert len(groups[0].rows) == 2


def test_disagreeing_nutrients_block_auto_accept():
    rows = [
        _row("usda", "Broccoli, raw", calories_per_100g=34.0),
        _row("ciqual", "raw broccoli", calories_per_100g=250.0),
    ]
    groups = group_foods(rows)
    assert groups[0].auto_accepted is False


def test_different_prep_state_never_groups():
    rows = [
        _row("usda", "Potato, raw", calories_per_100g=77.0),
        _row("cofid", "Potato, boiled", calories_per_100g=87.0),
    ]
    groups = group_foods(rows)
    assert len(groups) == 2


def test_apply_decisions_requires_a_decision_for_every_conflict(tmp_path):
    rows = [
        _row("usda", "Broccoli, raw", calories_per_100g=34.0),
        _row("ciqual", "raw broccoli", calories_per_100g=250.0),
    ]
    groups = group_foods(rows)
    with pytest.raises(ValueError):
        apply_decisions(groups, {})

    p = tmp_path / "d.csv"
    p.write_text("group_id,decision,canonical_name,note\n%s,separate,,\n" % groups[0].group_id)
    resolved = apply_decisions(groups, load_decisions(str(p)))
    assert len(resolved) == 2
```

- [x] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/build_food_db/test_match.py -v`
Expected: FAIL — `ModuleNotFoundError: scripts.build_food_db.match`

- [x] **Step 3: Implement `match.py`**

```python
# scripts/build_food_db/match.py
import csv
from dataclasses import dataclass, field
from typing import Dict, List

from rapidfuzz import fuzz

from scripts.build_food_db.model import NUTRIENT_FIELDS, NormalisedRow

TOKEN_SET_THRESHOLD = 92
NUTRIENT_TOLERANCE = 0.25
NUTRIENT_ABS_FLOOR = 0.5


@dataclass
class MergeGroup:
    group_id: str
    canonical_name: str
    rows: List[NormalisedRow] = field(default_factory=list)
    auto_accepted: bool = True


def _nutrients_agree(rows: List[NormalisedRow]) -> bool:
    for f in NUTRIENT_FIELDS:
        vals = [v for v in (getattr(r, f) for r in rows) if v is not None]
        if len(vals) < 2:
            continue
        lo, hi = min(vals), max(vals)
        if hi - lo <= NUTRIENT_ABS_FLOOR:
            continue
        if lo <= 0:
            return False
        if (hi - lo) / lo > NUTRIENT_TOLERANCE:
            return False
    return True


def group_foods(rows: List[NormalisedRow]) -> List[MergeGroup]:
    buckets: Dict[tuple, List[NormalisedRow]] = {}
    for r in rows:
        buckets.setdefault((r.canonical_key, r.prep_state), []).append(r)

    keys = sorted(buckets)
    merged: List[List[str]] = []           # lists of exact-keys that fuzzy-merge
    used = set()
    for i, k in enumerate(keys):
        if k in used:
            continue
        cluster = [k]
        used.add(k)
        for k2 in keys[i + 1:]:
            if k2 in used or k2[1] != k[1]:
                continue
            if fuzz.token_set_ratio(k[0], k2[0]) >= TOKEN_SET_THRESHOLD:
                cluster.append(k2)
                used.add(k2)
        merged.append(cluster)

    groups: List[MergeGroup] = []
    for cluster in merged:
        rws: List[NormalisedRow] = []
        for k in cluster:
            rws.extend(buckets[k])
        gid = cluster[0][0].replace(" ", "_") + "__" + cluster[0][1]
        name = sorted(rws, key=lambda r: (r.source_id != "usda", len(r.name)))[0].name
        groups.append(MergeGroup(
            group_id=gid, canonical_name=name, rows=rws,
            auto_accepted=(len(cluster) == 1) or _nutrients_agree(rws),
        ))
    return sorted(groups, key=lambda g: g.group_id)


def write_conflicts(groups: List[MergeGroup], path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["group_id", "source_id", "name", "decision"] + list(NUTRIENT_FIELDS))
        for g in groups:
            if g.auto_accepted:
                continue
            for r in g.rows:
                w.writerow([g.group_id, r.source_id, r.name, ""]
                           + [getattr(r, f) for f in NUTRIENT_FIELDS])


def load_decisions(path: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            d = (row.get("decision") or "").strip()
            if d:
                out[row["group_id"]] = d
    return out


def apply_decisions(groups: List[MergeGroup], decisions: Dict[str, str]) -> List[MergeGroup]:
    missing = [g.group_id for g in groups if not g.auto_accepted and g.group_id not in decisions]
    if missing:
        raise ValueError("unresolved merge conflicts: " + ", ".join(sorted(missing)))
    out: List[MergeGroup] = []
    for g in groups:
        d = decisions.get(g.group_id, "merge")
        if d == "separate":
            for r in g.rows:
                out.append(MergeGroup(group_id=g.group_id + "__" + r.source_id,
                                      canonical_name=r.name, rows=[r]))
        elif d.startswith("rename:"):
            out.append(MergeGroup(group_id=g.group_id, canonical_name=d[len("rename:"):].strip(),
                                  rows=g.rows))
        else:
            out.append(g)
    return sorted(out, key=lambda g: g.group_id)
```

- [x] **Step 4: Run it to verify it passes**

Run: `python -m pytest tests/build_food_db/test_match.py -v`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add requirements.txt scripts/build_food_db/match.py tests/build_food_db/test_match.py
git commit -m "feat: cross-source food matching with committed conflict decisions"
```

---

## Task 6: Sanity filter & aggregation

**Files:**
- Create: `scripts/build_food_db/aggregate.py`
- Test: `tests/build_food_db/test_aggregate.py`

**Interfaces:**
- Consumes: `MergeGroup` (Task 5), `NUTRIENT_FIELDS` (Task 2).
- Produces:
  - `MAX_KCAL_PER_100G = 900.0`, `MAX_MACRO_SUM_PER_100G = 105.0` — module constants.
  - `sanity_ok(field: str, value: float, row_nutrients: Dict[str, Optional[float]]) -> bool` — applies the Global-Constraints rules to one source value.
  - `AggregatedFood` dataclass: `canonical_name: str`, `prep_state: str`, `category: Optional[str]`, `source_ids: List[str]`, `source_count: int`, one `Optional[float]` per `NUTRIENT_FIELDS`.
  - `aggregate_group(group: MergeGroup) -> Optional[AggregatedFood]` — returns `None` when no nutrient has ≥ 2 surviving values.

- [x] **Step 1: Write the failing test**

```python
# tests/build_food_db/test_aggregate.py
from scripts.build_food_db.model import NormalisedRow
from scripts.build_food_db.match import MergeGroup
from scripts.build_food_db.aggregate import aggregate_group, sanity_ok


def _r(src, **nut):
    return NormalisedRow(source_id=src, source_food_id=src, name="x",
                         canonical_key="x", prep_state="raw", **nut)


def test_median_when_three_sources_mean_when_two():
    g = MergeGroup("x__raw", "X", [
        _r("a", calories_per_100g=10.0, protein_per_100g=1.0),
        _r("b", calories_per_100g=20.0, protein_per_100g=3.0),
        _r("c", calories_per_100g=90.0),
    ])
    out = aggregate_group(g)
    assert out.calories_per_100g == 20.0      # median(10,20,90)
    assert out.protein_per_100g == 2.0        # mean(1,3)
    assert out.source_count == 3
    assert out.source_ids == ["a", "b", "c"]


def test_impossible_calorie_value_is_dropped_before_aggregation():
    g = MergeGroup("x__raw", "X", [
        _r("a", calories_per_100g=0.0),
        _r("b", calories_per_100g=10000.0),
        _r("c", calories_per_100g=2.0),
    ])
    out = aggregate_group(g)
    assert out.calories_per_100g == 1.0       # median(0, 2) after dropping 10000

def test_group_with_no_nutrient_reaching_two_sources_returns_none():
    g = MergeGroup("x__raw", "X", [_r("a", calories_per_100g=5.0)])
    assert aggregate_group(g) is None


def test_sanity_rules():
    assert sanity_ok("calories_per_100g", 500.0, {}) is True
    assert sanity_ok("calories_per_100g", 901.0, {}) is False
    assert sanity_ok("protein_per_100g", -1.0, {}) is False
    assert sanity_ok("carbs_per_100g", 60.0,
                     {"protein_per_100g": 30.0, "fat_per_100g": 20.0,
                      "carbs_per_100g": 60.0, "fiber_per_100g": 0.0}) is False
```

- [x] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/build_food_db/test_aggregate.py -v`
Expected: FAIL — `ModuleNotFoundError: scripts.build_food_db.aggregate`

- [x] **Step 3: Implement `aggregate.py`**

```python
# scripts/build_food_db/aggregate.py
from dataclasses import dataclass
from statistics import mean, median
from typing import Dict, List, Optional

from scripts.build_food_db.model import NUTRIENT_FIELDS
from scripts.build_food_db.match import MergeGroup

MAX_KCAL_PER_100G = 900.0
MAX_MACRO_SUM_PER_100G = 105.0
_MACROS = ("protein_per_100g", "fat_per_100g", "carbs_per_100g", "fiber_per_100g")


@dataclass
class AggregatedFood:
    canonical_name: str
    prep_state: str
    category: Optional[str]
    source_ids: List[str]
    source_count: int
    calories_per_100g: Optional[float] = None
    protein_per_100g: Optional[float] = None
    fat_per_100g: Optional[float] = None
    carbs_per_100g: Optional[float] = None
    fiber_per_100g: Optional[float] = None
    sugar_per_100g: Optional[float] = None
    sodium_mg_per_100g: Optional[float] = None
    calcium_mg_per_100g: Optional[float] = None
    iron_mg_per_100g: Optional[float] = None
    vitamin_c_mg_per_100g: Optional[float] = None
    vitamin_d_mcg_per_100g: Optional[float] = None
    vitamin_b12_mcg_per_100g: Optional[float] = None


def sanity_ok(field: str, value: float, row_nutrients: Dict[str, Optional[float]]) -> bool:
    if value < 0:
        return False
    if field == "calories_per_100g" and value > MAX_KCAL_PER_100G:
        return False
    if field in _MACROS:
        s = sum((row_nutrients.get(m) or 0.0) for m in _MACROS)
        if s > MAX_MACRO_SUM_PER_100G:
            return False
    return True


def aggregate_group(group: MergeGroup) -> Optional[AggregatedFood]:
    source_ids = sorted({r.source_id for r in group.rows})
    out = AggregatedFood(
        canonical_name=group.canonical_name,
        prep_state=group.rows[0].prep_state,
        category=next((r.category for r in group.rows if r.category), None),
        source_ids=source_ids,
        source_count=len(source_ids),
    )
    any_nutrient = False
    for f in NUTRIENT_FIELDS:
        vals = []
        for r in group.rows:
            v = getattr(r, f)
            if v is not None and sanity_ok(f, v, r.nutrients()):
                vals.append(v)
        if len(vals) >= 3:
            setattr(out, f, round(median(vals), 4))
            any_nutrient = True
        elif len(vals) == 2:
            setattr(out, f, round(mean(vals), 4))
            any_nutrient = True
    return out if any_nutrient else None
```

- [x] **Step 4: Run it to verify it passes**

Run: `python -m pytest tests/build_food_db/test_aggregate.py -v`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add scripts/build_food_db/aggregate.py tests/build_food_db/test_aggregate.py
git commit -m "feat: sanity filter + median/mean aggregation for food-DB build"
```

---

## Task 7: FNDDS portion attachment

**Files:**
- Create: `scripts/build_food_db/portions.py`
- Create: `tests/build_food_db/fixtures/fndds_portions_slice.csv`
- Test: `tests/build_food_db/test_portions.py`

**Interfaces:**
- Consumes: `AggregatedFood` (Task 6), `canonical_key` (Task 3), `rapidfuzz`.
- Produces:
  - `PORTION_MATCH_THRESHOLD = 90` — module constant.
  - `load_fndds_portions(raw_dir: str) -> Dict[str, List[Dict[str, float]]]` — maps a portion food's `canonical_key` to `[{"unit": str, "grams": float}, ...]`. Reads the FNDDS portion + food files from `raw_dir/usda/` (names per Task 1 README).
  - `attach_portions(foods: List[AggregatedFood], portions: Dict[...]) -> List[Tuple[AggregatedFood, List[Dict[str, float]]]]` — for each food, exact `canonical_key` hit else best fuzzy hit `>= PORTION_MATCH_THRESHOLD` else `[]`.

- [x] **Step 1: Write the failing test**

```python
# tests/build_food_db/test_portions.py
from scripts.build_food_db.aggregate import AggregatedFood
from scripts.build_food_db.portions import attach_portions


def _food(name):
    return AggregatedFood(canonical_name=name, prep_state="raw", category=None,
                          source_ids=["usda", "cofid"], source_count=2,
                          calories_per_100g=1.0)


def test_exact_key_match_attaches_portions():
    portions = {"rice white": [{"unit": "cup", "grams": 186.0}]}
    out = attach_portions([_food("White rice")], portions)
    assert out[0][1] == [{"unit": "cup", "grams": 186.0}]


def test_no_match_yields_empty_portions():
    out = attach_portions([_food("Obscure gourd")], {"rice white": [{"unit": "cup", "grams": 186.0}]})
    assert out[0][1] == []
```

- [x] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/build_food_db/test_portions.py -v`
Expected: FAIL — `ModuleNotFoundError: scripts.build_food_db.portions`

- [x] **Step 3: Implement `portions.py`**

```python
# scripts/build_food_db/portions.py
import os
from typing import Dict, List, Tuple

from rapidfuzz import fuzz, process

from scripts.build_food_db.aggregate import AggregatedFood
from scripts.build_food_db.normalise import canonical_key
from scripts.build_food_db.sources.base import read_csv_rows, parse_float

PORTION_MATCH_THRESHOLD = 90


def load_fndds_portions(raw_dir: str) -> Dict[str, List[Dict[str, float]]]:
    usda = os.path.join(raw_dir, "usda")
    # portion file: columns (fdc_id, portion_description / modifier, gram_weight)
    # food file already copied by the USDA extractor step; re-read for names.
    names: Dict[str, str] = {
        r["fdc_id"]: r["description"]
        for r in read_csv_rows(os.path.join(usda, "food.csv"))
    }
    out: Dict[str, List[Dict[str, float]]] = {}
    for r in read_csv_rows(os.path.join(usda, "food_portion.csv")):
        fid = r["fdc_id"]
        if fid not in names:
            continue
        unit = (r.get("portion_description") or r.get("modifier") or "").strip().lower()
        grams = parse_float(r.get("gram_weight"))
        if not unit or grams is None:
            continue
        key = canonical_key(names[fid])
        out.setdefault(key, [])
        if not any(p["unit"] == unit for p in out[key]):
            out[key].append({"unit": unit, "grams": round(grams, 2)})
    for key in out:
        out[key].sort(key=lambda p: p["unit"])
    return out


def attach_portions(foods: List[AggregatedFood],
                    portions: Dict[str, List[Dict[str, float]]]
                    ) -> List[Tuple[AggregatedFood, List[Dict[str, float]]]]:
    keys = list(portions)
    result = []
    for food in foods:
        k = canonical_key(food.canonical_name)
        if k in portions:
            result.append((food, portions[k]))
            continue
        match = process.extractOne(k, keys, scorer=fuzz.token_set_ratio,
                                   score_cutoff=PORTION_MATCH_THRESHOLD)
        result.append((food, portions[match[0]] if match else []))
    return result
```

- [x] **Step 4: Run it to verify it passes**

Run: `python -m pytest tests/build_food_db/test_portions.py -v`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add scripts/build_food_db/portions.py tests/build_food_db/fixtures/fndds_portions_slice.csv tests/build_food_db/test_portions.py
git commit -m "feat: attach USDA FNDDS household portions to aggregated foods"
```

---

## Task 8: Build orchestration & artifact writer

**Files:**
- Create: `scripts/build_food_db/build.py`
- Create: `tests/build_food_db/fixtures/mini/` — a self-contained fixture set: 2–3 source slices with overlapping foods + a small FNDDS portions slice, enough to exercise every stage.
- Test: `tests/build_food_db/test_build_golden.py`

**Interfaces:**
- Consumes: everything from Tasks 3–7, plus `ALL_SOURCES` (Task 4).
- Produces:
  - `FOODS_TABLE_DDL: str` — the `CREATE TABLE foods (...)` statement (columns per Global Constraints + `id TEXT PRIMARY KEY`, `canonical_name`, `aliases`, `category`, `prep_state`, `portions`, `source_ids`, `source_count`).
  - `build(source_rows: List[NormalisedRow], fndds_portions: Dict, decisions: Dict[str,str], out_path: str) -> None` — the pure core: group → apply decisions → aggregate → attach portions → assign `id` (`gen:00001`… by sorted `canonical_name`+`prep_state`) → write SQLite. `aliases` = sorted distinct source names in the group as a JSON array.
  - `main() -> None` — reads real raw dir + `review/decisions.csv`, calls `build`, writes `data/foods.sqlite`; regenerates `review/conflicts.csv` and exits non-zero (printing the count) if any conflict is unresolved.

- [x] **Step 1: Write the failing golden test**

```python
# tests/build_food_db/test_build_golden.py
import sqlite3
from scripts.build_food_db.model import NormalisedRow
from scripts.build_food_db.normalise import normalise_row
from scripts.build_food_db.build import build


def _r(src, name, **nut):
    return normalise_row(NormalisedRow(source_id=src, source_food_id=src + name, name=name, **nut))


def test_build_produces_deterministic_foods_table(tmp_path):
    rows = [
        _r("usda", "Broccoli, raw", calories_per_100g=34.0, protein_per_100g=2.8),
        _r("cofid", "raw broccoli", calories_per_100g=33.0, protein_per_100g=3.0),
        _r("ciqual", "broccoli raw", calories_per_100g=35.0, protein_per_100g=2.9),
        _r("usda", "Water, tap, drinking", calories_per_100g=0.0),
        _r("cofid", "tap water", calories_per_100g=0.0),
    ]
    portions = {"broccoli": [{"unit": "cup chopped", "grams": 91.0}]}

    out = tmp_path / "foods.sqlite"
    build(rows, portions, {}, str(out))
    build(rows, portions, {}, str(out))     # twice: must be identical

    con = sqlite3.connect(str(out))
    got = con.execute(
        "SELECT id, canonical_name, prep_state, calories_per_100g, source_count, portions "
        "FROM foods ORDER BY id"
    ).fetchall()
    con.close()

    assert got == [
        ("gen:00001", "Broccoli, raw", "raw", 34.0, 3, '[{"unit": "cup chopped", "grams": 91.0}]'),
        ("gen:00002", "Water, tap, drinking", "unspecified", 0.0, 2, "[]"),
    ]


def test_build_raises_on_unresolved_conflict(tmp_path):
    rows = [
        _r("usda", "Broccoli, raw", calories_per_100g=34.0),
        _r("ciqual", "raw broccoli", calories_per_100g=400.0),
    ]
    import pytest
    with pytest.raises(ValueError):
        build(rows, {}, {}, str(tmp_path / "x.sqlite"))
```

- [x] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/build_food_db/test_build_golden.py -v`
Expected: FAIL — `ModuleNotFoundError: scripts.build_food_db.build`

- [x] **Step 3: Implement `build.py`**

```python
# scripts/build_food_db/build.py
import json
import os
import sqlite3
from typing import Dict, List

from scripts.build_food_db.model import NUTRIENT_FIELDS, NormalisedRow
from scripts.build_food_db.match import group_foods, apply_decisions, write_conflicts, load_decisions
from scripts.build_food_db.aggregate import aggregate_group
from scripts.build_food_db.portions import attach_portions, load_fndds_portions
from scripts.build_food_db.sources import ALL_SOURCES

_NUT_COLS = ",\n  ".join("%s REAL" % f for f in NUTRIENT_FIELDS)
FOODS_TABLE_DDL = (
    "CREATE TABLE foods (\n"
    "  id TEXT PRIMARY KEY,\n"
    "  canonical_name TEXT NOT NULL,\n"
    "  aliases TEXT NOT NULL,\n"
    "  category TEXT,\n"
    "  prep_state TEXT NOT NULL,\n"
    "  " + _NUT_COLS + ",\n"
    "  portions TEXT NOT NULL,\n"
    "  source_ids TEXT NOT NULL,\n"
    "  source_count INTEGER NOT NULL\n"
    ")"
)


def build(source_rows: List[NormalisedRow], fndds_portions: Dict[str, list],
          decisions: Dict[str, str], out_path: str) -> None:
    groups = group_foods(source_rows)
    groups = apply_decisions(groups, decisions)          # raises on unresolved

    aggregated = []
    for g in groups:
        af = aggregate_group(g)
        if af is not None:
            aggregated.append((af, g))

    with_portions = attach_portions([af for af, _ in aggregated], fndds_portions)

    ordered = sorted(
        zip(aggregated, (p for _, p in with_portions)),
        key=lambda pair: (pair[0][0].canonical_name.lower(), pair[0][0].prep_state),
    )

    if os.path.exists(out_path):
        os.remove(out_path)
    con = sqlite3.connect(out_path)
    con.execute(FOODS_TABLE_DDL)
    for i, ((af, group), portions) in enumerate(ordered, start=1):
        aliases = sorted({r.name for r in group.rows})
        con.execute(
            "INSERT INTO foods VALUES (%s)" % ",".join(["?"] * (7 + len(NUTRIENT_FIELDS))),
            [
                "gen:%05d" % i, af.canonical_name, json.dumps(aliases),
                af.category, af.prep_state,
                *[getattr(af, f) for f in NUTRIENT_FIELDS],
                json.dumps(portions), json.dumps(af.source_ids), af.source_count,
            ],
        )
    con.commit()
    con.close()


def main() -> None:
    root = os.path.dirname(__file__)
    raw = os.path.join(root, "raw")
    rows: List[NormalisedRow] = []
    for src in ALL_SOURCES:
        rows.extend(src.extract(raw))
    portions = load_fndds_portions(raw)

    groups = group_foods(rows)
    write_conflicts(groups, os.path.join(root, "review", "conflicts.csv"))
    decisions = load_decisions(os.path.join(root, "review", "decisions.csv"))

    unresolved = [g.group_id for g in groups if not g.auto_accepted and g.group_id not in decisions]
    if unresolved:
        raise SystemExit(
            "%d unresolved merge conflicts — resolve review/conflicts.csv into "
            "review/decisions.csv" % len(unresolved)
        )

    out = os.path.join(os.path.dirname(os.path.dirname(root)), "data", "foods.sqlite")
    build(rows, portions, decisions, out)
    print("wrote", out)


if __name__ == "__main__":
    main()
```

- [x] **Step 4: Run it to verify it passes**

Run: `python -m pytest tests/build_food_db/test_build_golden.py -v`
Expected: PASS

- [x] **Step 5: Run the whole build-pipeline suite**

Run: `python -m pytest tests/build_food_db/ -v`
Expected: PASS (all tasks)

- [x] **Step 6: Commit**

```bash
git add scripts/build_food_db/build.py tests/build_food_db/fixtures/mini/ tests/build_food_db/test_build_golden.py
git commit -m "feat: food-DB build orchestration and deterministic SQLite artifact"
```

---

## Task 9: Generate & commit the real artifact

**Files:**
- Create: `data/foods.sqlite` (the generated artifact)
- Modify: `docs/food-data-sources.md` (fill in final counts + attribution block)
- Modify: `scripts/build_food_db/review/decisions.csv` (the resolved conflicts)

**Interfaces:**
- Consumes: `main()` from Task 8, the real downloads placed under `scripts/build_food_db/raw/` per the Task 1 README.

This task has no unit test — its deliverable is the committed artifact plus a sanity script.

**Expect on the first real run:** a large `review/conflicts.csv` (thousands of
rows at ~15k merged foods) and a slow build (the full national tables are
hundreds of thousands of rows; `rapidfuzz` clustering dominates). Plan to
iterate: tune `MACRO_TOLERANCE` / `MICRO_TOLERANCE` in `match.py` down until the
review list is a few hundred rows, and pin each xlsx source's real data-sheet
name and column spellings into its `SHEET` / `COLS` map in `sources/<id>.py`
against the actual downloaded files (the committed values are best-guesses from
the fixture slices).

- [ ] **Step 1: Download every confirmed source**

Follow `scripts/build_food_db/README.md`. Place files under `scripts/build_food_db/raw/<source_id>/` exactly as the README names them.

- [ ] **Step 2: First build run — generate conflicts**

Run: `python -m scripts.build_food_db.build`
Expected: exits non-zero, "<N> unresolved merge conflicts", `review/conflicts.csv` written.

- [ ] **Step 3: Resolve conflicts**

Open `review/conflicts.csv`. For each group, decide `merge` / `separate` / `rename:<name>` and record it in `review/decisions.csv` (columns `group_id,decision,canonical_name,note`). Spot-check by eye — the nutrient columns are in the CSV to make disagreements obvious.

- [ ] **Step 4: Second build run — produce the artifact**

Run: `python -m scripts.build_food_db.build`
Expected: "wrote .../data/foods.sqlite".

- [ ] **Step 5: Sanity-check the artifact**

Run this one-off check:

```bash
python -c "
import sqlite3
c = sqlite3.connect('data/foods.sqlite')
n, = c.execute('SELECT count(*) FROM foods').fetchone()
bad, = c.execute('SELECT count(*) FROM foods WHERE calories_per_100g > 900 OR calories_per_100g < 0').fetchone()
solo, = c.execute('SELECT count(*) FROM foods WHERE source_count < 2').fetchone()
noport, = c.execute(\"SELECT count(*) FROM foods WHERE portions = '[]'\").fetchone()
print('foods:', n, ' impossible-kcal:', bad, ' single-source:', solo, ' no-portions:', noport)
for name in ('water','broccoli','potato'):
    r = c.execute('SELECT canonical_name, calories_per_100g, source_count FROM foods WHERE canonical_name LIKE ?', ('%'+name+'%',)).fetchone()
    print(name, '->', r)
"
```

Expected: `impossible-kcal: 0`, `single-source: 0`, a plausible `foods` count (~10k–20k), and `water` at ~0 kcal.

- [ ] **Step 6: Rebuild once more, confirm byte-identical**

```bash
cp data/foods.sqlite /tmp/foods-a.sqlite
python -m scripts.build_food_db.build
cmp data/foods.sqlite /tmp/foods-a.sqlite && echo DETERMINISTIC
```

Expected: `DETERMINISTIC`.

- [ ] **Step 7: Fill in `docs/food-data-sources.md`**

Add the final food count, per-source contributed-row counts (from `source_ids`), and a consolidated **Attribution** section with every licence's required credit string verbatim.

- [ ] **Step 8: Commit**

```bash
git add data/foods.sqlite docs/food-data-sources.md scripts/build_food_db/review/decisions.csv
git commit -m "feat: generate multi-country averaged food database artifact"
```

---

## Self-Review

**Spec coverage:**

- Sources & licensing → Task 1 (verification + register), Task 4 (one extractor per confirmed source). ✓
- Cross-source identity (canonical key + prep state) → Task 3. ✓
- Conflict review CSV + committed decisions → Task 5, resolved in Task 9. ✓
- Sanity filter (kcal ≤ 900, macro sum ≤ 105, non-negative) → Task 6 (`sanity_ok`), asserted in Task 6 + Task 9 Step 5. ✓
- Averaging (median ≥ 3, mean 2, null < 2; ≥ 2-source emit rule) → Task 6. ✓
- FNDDS portions side-table, name-matched → Task 7. ✓
- `scripts/build_food_db/` layout → Tasks 2–8 match the spec's file list. ✓
- Committed `data/foods.sqlite`, deterministic → Task 8 (ordering, no timestamps) + Task 9 Step 6 (`cmp`). ✓
- `docs/food-data-sources.md` + in-app attribution → doc in Tasks 1/9; **in-app** Settings credits line is runtime and belongs to the second plan — noted here, not built.
- Raw files not committed → Task 1 `.gitignore`. ✓
- `foods` table schema → `FOODS_TABLE_DDL` in Task 8 matches the spec's column table (minus runtime-only concerns). ✓

**Not in this plan (second plan — runtime cutover):** `food_index.py`, `/foods*` route changes, `recipe_import.py` collapse, `usda.py` retirement from request paths, `fdc_id → food_id` migration, `schemas.py`, `create_tables.py` seeding, frontend changes, the Settings attribution line. Those consume `data/foods.sqlite` produced here.

**Placeholder scan:** No "TBD"/"handle errors"/"similar to Task N". The one soft spot is Task 4 Step 12 (non-USDA extractors described as a repeat of the USDA pattern rather than fully written) — unavoidable without the real source files in hand; mitigated by the fixed `NormalisedRow` contract, the per-source fixture-slice test requirement, and the fully-worked USDA reference. Flagged, not hidden.

**Type consistency:** `NormalisedRow` (Task 2) is the currency through Tasks 3–8. `MergeGroup` (Task 5) → `aggregate_group` (Task 6). `AggregatedFood` (Task 6) → `attach_portions` (Task 7) → `build` (Task 8). `NUTRIENT_FIELDS` names are fixed in Global Constraints and reused verbatim in the DDL and every dataclass. `canonical_key` / `parse_prep_state` (Task 3) used by Tasks 4, 5, 7. Constant names (`TOKEN_SET_THRESHOLD`, `MAX_KCAL_PER_100G`, `PORTION_MATCH_THRESHOLD`) are each defined once. ✓
