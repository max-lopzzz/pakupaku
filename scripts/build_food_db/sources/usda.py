import os
from typing import Dict, List

from scripts.build_food_db.model import NormalisedRow
from scripts.build_food_db.normalise import normalise_row
from scripts.build_food_db.sources.base import Source, read_csv_rows, parse_float

# USDA FoodData Central multi-file CSV release. Schema is stable and
# documented: food.csv, food_nutrient.csv, nutrient.csv.
COLS = {
    "food": {
        "id": "fdc_id",
        "data_type": "data_type",
        "name": "description",
        "category": "food_category_id",
    },
    "food_nutrient": {
        "food_id": "fdc_id",
        "nutrient_id": "nutrient_id",
        "amount": "amount",
    },
}

# USDA nutrient id -> NormalisedRow field. food_nutrient.amount is already
# in the nutrient's own unit (g for macros, mg for 1093/1087/1089/1162,
# ug for 1110/1178), matching the NormalisedRow field units, so assign
# directly (factor 1.0).
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
# generic/whole-food rows only — exclude branded_food and survey_fndds_food
_GENERIC_TYPES = {"foundation_food", "sr_legacy_food"}


class _Usda(Source):
    id = "usda"

    def extract(self, raw_dir: str) -> List[NormalisedRow]:
        fc = COLS["food"]
        nc = COLS["food_nutrient"]
        foods = {
            r[fc["id"]]: r
            for r in read_csv_rows(os.path.join(raw_dir, "food.csv"))
            if r.get(fc["data_type"]) in _GENERIC_TYPES
        }
        rows: Dict[str, NormalisedRow] = {}
        for fdc_id, f in foods.items():
            rows[fdc_id] = NormalisedRow(
                source_id="usda", source_food_id=fdc_id,
                name=f[fc["name"]].strip(),
                category=(f.get(fc["category"]) or None),
            )
        for fn in read_csv_rows(os.path.join(raw_dir, "food_nutrient.csv")):
            fid = fn[nc["food_id"]]
            if fid not in rows:
                continue
            mapping = _NUTRIENT_MAP.get(fn[nc["nutrient_id"]])
            if not mapping:
                continue
            field, factor = mapping
            val = parse_float(fn.get(nc["amount"]))
            if val is not None:
                setattr(rows[fid], field, round(val * factor, 4))
        return [normalise_row(r) for r in rows.values()]


SOURCE = _Usda()
