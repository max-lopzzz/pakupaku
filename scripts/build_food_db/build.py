import json
import os
import sqlite3
from typing import Dict, List, Optional

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
            "INSERT INTO foods VALUES (%s)" % ",".join(["?"] * (8 + len(NUTRIENT_FIELDS))),
            [
                "gen:%05d" % i, af.canonical_name, json.dumps(aliases),
                af.category, af.prep_state,
                *[getattr(af, f) for f in NUTRIENT_FIELDS],
                json.dumps(portions), json.dumps(af.source_ids), af.source_count,
            ],
        )
    con.commit()
    con.close()


def main(root: Optional[str] = None, out_path: Optional[str] = None) -> None:
    """Run the whole build.

    ``root`` is the package dir holding ``raw/`` and ``review/`` (defaults to
    this module's own dir); ``out_path`` defaults to ``<repo>/data/foods.sqlite``.
    Both are parameters so the pipeline can be driven end-to-end from a test.
    """
    root = root or os.path.dirname(__file__)
    raw = os.path.join(root, "raw")
    review = os.path.join(root, "review")
    os.makedirs(review, exist_ok=True)

    rows: List[NormalisedRow] = []
    for src in ALL_SOURCES:
        # every extractor joins its own filename onto the dir it is given,
        # so each one gets its own raw/<source_id>/ dir, not the raw root.
        rows.extend(src.extract(os.path.join(raw, src.id)))
    portions = load_fndds_portions(raw)

    groups = group_foods(rows)
    write_conflicts(groups, os.path.join(review, "conflicts.csv"))
    decisions = load_decisions(os.path.join(review, "decisions.csv"))

    unresolved = [g.group_id for g in groups if not g.auto_accepted and g.group_id not in decisions]
    if unresolved:
        raise SystemExit(
            "%d unresolved merge conflicts — resolve review/conflicts.csv into "
            "review/decisions.csv" % len(unresolved)
        )

    out = out_path or os.path.join(
        os.path.dirname(os.path.dirname(root)), "data", "foods.sqlite")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    build(rows, portions, decisions, out)
    print("wrote", out)


if __name__ == "__main__":
    main()
