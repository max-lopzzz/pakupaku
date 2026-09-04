# `mini/` — end-to-end build fixture slice

A tiny, self-contained input set that drives the **whole** food-DB build
pipeline (Tasks 3–8) from real extractor input through to the SQLite
artifact, without needing any of the multi-thousand-row national releases.

Used by `tests/build_food_db/test_build_golden.py::test_build_mini_end_to_end`
and by the two `main()` tests in the same module.

## Contents

| file | role | notes |
|------|------|-------|
| `cofid_2021.csv` | UK CoFID per-100g slice (`cofid` extractor input) | 4 rows: two near-duplicate broccoli rows and two near-duplicate carrot rows, so cross-row **matching + aggregation** actually merge and emit foods. Kept as CSV for readable diffs — the tests convert it to the `.xlsx` workbook the extractor actually opens (`conftest.csv_to_xlsx` / `cofid_raw_dir`). |
| `usda/food.csv` | FDC food slice (`usda` extractor + `load_fndds_portions` input) | `fdc_id, data_type, description, food_category_id` for the same two foods. |
| `usda/food_nutrient.csv` | FDC nutrient slice (`usda` extractor input) | energy / protein / vitamin C only — the **second source** each nutrient needs. |
| `usda/food_portion.csv` | FDC household-portion slice | `cup chopped` gram weights for broccoli and carrots. |

## Why two sources, and why the duplicate CoFID rows

`aggregate_group` emits a nutrient only when **≥ 2 distinct sources** still
have a sane value for it — two rows fuzzy-merged out of the *same* national
table count once. So the slice needs a real second source: the small `usda`
nutrient slice supplies energy, protein and vitamin C for both foods, and
those are the only three columns the built artifact carries. The remaining
CoFID-only nutrients (fat, sodium, …) stay `NULL` on purpose — that is the
rule under test.

The duplicated CoFID rows (`"Broccoli, raw"` / `"raw broccoli"`, both →
canonical key `broccoli`) stay because they exercise the fuzzy merge *and*
the same-source averaging step: CoFID's 33 and 35 kcal collapse to one 34
kcal contribution before the cross-source mean.

## Stages exercised

extractor → `normalise_row` → `group_foods` (fuzzy merge) →
`apply_decisions` (all auto-accepted) → `aggregate_group` (per-source mean,
then cross-source mean of 2) →
`load_fndds_portions` + `attach_portions` (exact canonical-key hit) →
`id` assignment → deterministic SQLite write (built twice, bytes compared).
