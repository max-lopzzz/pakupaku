# `scripts/build_food_db/` — offline multi-country food database build

Builds `data/foods.sqlite` (one canonical generic food per row, each nutrient a
median/mean across national food-composition tables). Manual, occasional
operation — run it when a source publishes a new edition.

- Design: `docs/superpowers/specs/2026-09-03-multi-country-food-database-design.md`
- Licence register (source of truth for which extractors exist):
  `docs/food-data-sources.md`

## Raw downloads

Raw source files are **not committed** (size + licence). They live under
`scripts/build_food_db/raw/<source_id>/`, which is git-ignored. Create the
directories as you download:

```
scripts/build_food_db/raw/
  usda/
  cofid/
  ciqual/
  afcd/
  cnf/
  frida/
```

Four regional sources (FAO West Africa, FAO Central & Eastern Africa, FAO ASEAN,
South Korea RDA) were evaluated and **rejected** on licence grounds
(non-commercial or commercial-by-fee) — see `docs/food-data-sources.md`. No
extractor is written for them; do not add `raw/` folders for them.

---

### `usda` — USDA FoodData Central  (public domain / CC0 1.0)

1. Go to https://fdc.nal.usda.gov/download-datasets/
2. Under **"Full Download of All Data Types"** download the **CSV** ZIP (latest
   release, e.g. December 2025 — ~458 MB zipped, ~3 GB unzipped).
3. Unzip into `scripts/build_food_db/raw/usda/`. Keep only these files (delete
   the rest to save space):
   - `food.csv` — read by `sources/usda.py` (generic-food rows) **and**
     `portions.py` (household-measure names, restricted to
     `foundation_food` / `sr_legacy_food` / `survey_fndds_food`).
   - `food_nutrient.csv` — read by `sources/usda.py`.
   - `food_portion.csv` — read by `portions.py`. The build divides
     `gram_weight` by `amount` (`amount=3, modifier="oz"` → grams per oz),
     falling back to the raw `gram_weight` when `amount` is blank / 0 / 1.
   - `nutrient.csv` — **not currently read by any extractor**; keep it only as
     a reference for the `sources/usda.py` nutrient-id map.

No separate FNDDS release is needed: the household portions come from
`food_portion.csv` in this Full Download, not from the standalone
FNDDS 2021-2023 CSV release.

Final layout:

```
raw/usda/food.csv
raw/usda/food_nutrient.csv
raw/usda/food_portion.csv
raw/usda/nutrient.csv         (reference only — no extractor reads it)
```

---

### `cofid` — UK CoFID  (Open Government Licence v3.0)

1. Go to https://www.gov.uk/government/publications/composition-of-foods-integrated-dataset-cofid
2. Download **"McCance and Widdowson's The Composition of Foods Integrated
   Dataset 2021"** (Excel, ~4.4 MB). The **"...composition of foods: old
   foods"** workbook on the same page is *not* read by any extractor — skip it.
3. Put the workbook in `scripts/build_food_db/raw/cofid/` under exactly the
   name `sources/cofid.py` opens (`FILE`):
   - `raw/cofid/McCance_Widdowsons_Composition_of_Foods_Integrated_Dataset_2021.xlsx`
4. Open the workbook, note the sheet carrying the per-100 g columns, and pin it
   as `SHEET` in `sources/cofid.py` (currently the best-guess
   `"1.3 Proximates"`). Pin the header spellings into that module's `COLS`
   map at the same time — the published edition spreads proximates,
   inorganics and vitamins over separate sheets.

---

### `ciqual` — France CIQUAL / ANSES  (Licence Ouverte / Etalab 2.0)

1. Go to https://ciqual.anses.fr/ → the download page, or
   https://www.data.gouv.fr/datasets/table-de-composition-nutritionnelle-des-aliments-ciqual-2020
2. Download the **Ciqual 2025** table as **Excel** (`.xls` / `.xlsx`).
3. Put it in `scripts/build_food_db/raw/ciqual/`:
   - `raw/ciqual/Table_Ciqual_2025.xlsx`

Note: CIQUAL ships as `xls` — `openpyxl` may need the file re-saved as `xlsx`, or
read the XML export instead.

---

### `afcd` — Australian Food Composition Database / FSANZ  (CC BY-SA 3.0 AU)

1. Go to https://www.foodstandards.gov.au/science-data/food-nutrient-databases/afcd/data-files
2. Download the **Release 2** downloadable Excel files (food details, per-100 g
   nutrients, measures). (Pin Release 2 for a deterministic build; Release 3.0 is
   also acceptable if the extractor is updated to match.)
3. Put them in `scripts/build_food_db/raw/afcd/`:
   - `raw/afcd/Release2_Food_Details.xlsx`
   - `raw/afcd/Release2_Food_Nutrients_per_100g.xlsx`
   - `raw/afcd/Release2_Food_Measures.xlsx`

Carry the FSANZ **Limitation of Data Statement** and the CC BY-SA 3.0 AU notice
with the build output (already in `docs/food-data-sources.md`).

---

### `cnf` — Canadian Nutrient File / Health Canada  (Open Government Licence – Canada)

1. Go to https://open.canada.ca/data/en/dataset/089885f9-ed53-44e6-854a-14d21a1ec2e0
2. Download the **CNF 2015** release in **CSV** (multi-file relational ZIP).
3. Unzip into `scripts/build_food_db/raw/cnf/`. Files used (confirm exact names
   on download — the 2015 release uses spaces in filenames):
   - `FOOD NAME.csv`
   - `NUTRIENT AMOUNT.csv`
   - `NUTRIENT NAME.csv`
   - `CONVERSION FACTOR.csv`
   - `MEASURE NAME.csv`

---

### `frida` — Frida, Danish Food Composition Database / DTU  (free reuse with citation)

1. Go to https://frida.fooddata.dk/ → **"Download Frida dataset"**
   (https://frida.fooddata.dk/data).
2. Submit the form; a download link for the **version 5.3 (November 2024)**
   spreadsheet arrives by email. (Version 5.5 (2025) is acceptable if the
   extractor matches.)
3. Put it in `scripts/build_food_db/raw/frida/`:
   - `raw/frida/Frida_5.3.xlsx`

---

## Run the build

From the repo root, with the virtualenv active and all `raw/<source_id>/` folders
populated:

```
python -m scripts.build_food_db.build
```

This runs every extractor in `ALL_SOURCES`, normalises names, fuzzy-matches
across sources, applies the sanity filter, aggregates (median ≥ 3 sources, mean
for 2), attaches FNDDS portions, and writes `data/foods.sqlite`.

- Unresolved conflicts are written to `review/conflicts.csv` (git-ignored) and
  **fail the build** until each row is resolved in `review/decisions.csv`
  (committed).
- The build is idempotent: same `raw/` inputs + `review/decisions.csv` +
  `translations/` → byte-identical `data/foods.sqlite`.
