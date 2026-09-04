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
