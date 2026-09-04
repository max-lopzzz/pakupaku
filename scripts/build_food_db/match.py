# scripts/build_food_db/match.py
import csv
from dataclasses import dataclass, field
from statistics import median
from typing import Dict, List

from rapidfuzz import fuzz

from scripts.build_food_db.model import NUTRIENT_FIELDS, NormalisedRow

TOKEN_SET_THRESHOLD = 92
# Macros are measured the same way everywhere and should agree closely;
# micronutrients vary a lot between national tables for legitimate reasons
# (soil, cultivar, fortification, assay method), so a uniform tolerance
# would flood the review list with non-conflicts.
MACRO_FIELDS = (
    "calories_per_100g", "protein_per_100g", "fat_per_100g",
    "carbs_per_100g", "fiber_per_100g",
)
# Starting values — tune both against the real conflicts.csv on the first
# full build run (see the plan's Task 9).
MACRO_TOLERANCE = 0.25
MICRO_TOLERANCE = 0.60
# spreads at or below this many units are noise whatever the relative size
NUTRIENT_ABS_FLOOR = 0.5


@dataclass
class MergeGroup:
    group_id: str
    canonical_name: str
    rows: List[NormalisedRow] = field(default_factory=list)
    auto_accepted: bool = True


def _nutrients_agree(rows: List[NormalisedRow]) -> bool:
    """Do these rows describe the same food closely enough to auto-merge?

    The spread is compared to the *median* rather than the minimum: one
    outlying low value would otherwise inflate the relative spread and
    reject a group whose values are in fact tightly clustered.
    """
    for f in NUTRIENT_FIELDS:
        vals = [v for v in (getattr(r, f) for r in rows) if v is not None]
        if len(vals) < 2:
            continue
        spread = max(vals) - min(vals)
        if spread <= NUTRIENT_ABS_FLOOR:
            continue
        m = median(vals)
        if m <= 0:
            # no meaningful relative comparison; the absolute floor above is
            # the only test such a nutrient gets, and it already failed.
            return False
        tolerance = MACRO_TOLERANCE if f in MACRO_FIELDS else MICRO_TOLERANCE
        if spread / m > tolerance:
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
            auto_accepted=_nutrients_agree(rws),
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
