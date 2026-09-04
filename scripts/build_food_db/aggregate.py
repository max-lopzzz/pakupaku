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
