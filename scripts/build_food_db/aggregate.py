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


MIN_SOURCES_PER_NUTRIENT = 2


def aggregate_group(group: MergeGroup) -> Optional[AggregatedFood]:
    """Aggregate one merge group into a single food, or ``None``.

    A nutrient is emitted only when at least ``MIN_SOURCES_PER_NUTRIENT``
    *distinct sources* still have a sane value for it — two rows that a fuzzy
    merge pulled in from the same national table are one source, not two, and
    would otherwise let a single table set ``source_count == 1`` in breach of
    the spec. Within a source the surviving values are averaged first, so each
    source contributes exactly one value; across sources it is the median from
    three sources up, the mean at exactly two.
    """
    out = AggregatedFood(
        canonical_name=group.canonical_name,
        prep_state=group.rows[0].prep_state,
        category=next((r.category for r in group.rows if r.category), None),
        source_ids=[],
        source_count=0,
    )
    contributing = set()
    for f in NUTRIENT_FIELDS:
        by_source: Dict[str, List[float]] = {}
        for r in group.rows:
            v = getattr(r, f)
            if v is not None and sanity_ok(f, v, r.nutrients()):
                by_source.setdefault(r.source_id, []).append(v)
        if len(by_source) < MIN_SOURCES_PER_NUTRIENT:
            continue
        # one value per source, in a deterministic order
        vals = [mean(by_source[sid]) for sid in sorted(by_source)]
        setattr(out, f, round(median(vals) if len(vals) >= 3 else mean(vals), 4))
        contributing.update(by_source)
    if not contributing:
        return None
    out.source_ids = sorted(contributing)
    out.source_count = len(out.source_ids)
    return out
