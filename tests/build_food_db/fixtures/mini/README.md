# `mini/` — end-to-end build fixture slice

A tiny, self-contained input set that drives the **whole** food-DB build
pipeline (Tasks 3–8) from real extractor input through to the SQLite
artifact, without needing any of the multi-thousand-row national releases.

Used by `tests/build_food_db/test_build_golden.py::test_build_mini_end_to_end`.

## Contents

| file | role | notes |
|------|------|-------|
| `cofid_2021.csv` | UK CoFID per-100g slice (`cofid` extractor input) | 4 rows: two near-duplicate broccoli rows and two near-duplicate carrot rows, so cross-row **matching + aggregation** actually merge and emit foods. |
| `usda/food.csv` | FNDDS food-name slice (`load_fndds_portions` input) | maps `fdc_id -> description`. |
| `usda/food_portion.csv` | FNDDS household-portion slice | `cup chopped` gram weights for broccoli and carrots. |

## Why the duplicate rows

`aggregate_group` only emits a food when a nutrient has **≥ 2** source
values. A single-source slice would therefore produce an empty table, so
each real food appears twice under names that normalise to the same
canonical key (`"Broccoli, raw"` / `"raw broccoli"` → `broccoli`).

## Stages exercised

extractor → `normalise_row` → `group_foods` (fuzzy merge) →
`apply_decisions` (all auto-accepted) → `aggregate_group` (mean of 2) →
`load_fndds_portions` + `attach_portions` (exact canonical-key hit) →
`id` assignment → deterministic SQLite write (built twice, bytes compared).
