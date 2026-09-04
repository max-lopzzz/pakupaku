import os
from typing import Dict, List

from scripts.build_food_db.model import NormalisedRow
from scripts.build_food_db.normalise import normalise_row
from scripts.build_food_db.sources.base import (
    Source, read_csv_rows, parse_float, kj_to_kcal,
)

# Canadian Nutrient File (CNF), 2026 full-file CSV release (open.canada.ca
# dataset 1b6139bd-ed7e-4043-bc28-ff00e10f3109). Files ship with a UTF-8 BOM,
# hence encoding="utf-8-sig" below.
FILES = {
    "food": "food_name.csv",
    "nutrient": "nutrient_name.csv",
    "amount": "nutrient_amount.csv",
}
COLS = {
    "food": {
        "id": "Food_Code",
        "name": "Food_Description_EN",
        "category": "CNF_Food_Group_Code",
    },
    "amount": {
        "food_id": "Food_Code",
        "nutrient_id": "Nutrient_Code",
        "value": "Nutrient_Amount",
    },
}
# CNF Nutrient_Code -> NormalisedRow field. NUTRIENT AMOUNT values are already
# per 100 g edible portion in the nutrient's own unit (g for macros, mg for
# minerals, ug for vitamin D / B-12), so no scaling is needed. Energy id 268
# (kJ) is used only as a fallback when 208 (kcal) is absent.
_NUTRIENT_MAP = {
    "208": "calories_per_100g",
    "203": "protein_per_100g",
    "204": "fat_per_100g",
    "205": "carbs_per_100g",
    "291": "fiber_per_100g",
    "269": "sugar_per_100g",
    "307": "sodium_mg_per_100g",
    "301": "calcium_mg_per_100g",
    "303": "iron_mg_per_100g",
    "401": "vitamin_c_mg_per_100g",
    "328": "vitamin_d_mcg_per_100g",
    "418": "vitamin_b12_mcg_per_100g",
}
_ENERGY_KJ_ID = "268"


class _Cnf(Source):
    id = "cnf"

    def extract(self, raw_dir: str) -> List[NormalisedRow]:
        fc = COLS["food"]
        ac = COLS["amount"]
        rows: Dict[str, NormalisedRow] = {}
        for f in read_csv_rows(os.path.join(raw_dir, FILES["food"]), encoding="utf-8-sig"):
            fid = (f.get(fc["id"]) or "").strip()
            if not fid:
                continue
            rows[fid] = NormalisedRow(
                source_id="cnf", source_food_id=fid,
                name=(f.get(fc["name"]) or "").strip(),
                category=None,  # raw source categories aren't reconciled yet (Plan-2)
            )
        kj_energy: Dict[str, float] = {}
        for a in read_csv_rows(os.path.join(raw_dir, FILES["amount"]), encoding="utf-8-sig"):
            fid = (a.get(ac["food_id"]) or "").strip()
            row = rows.get(fid)
            if row is None:
                continue
            nid = (a.get(ac["nutrient_id"]) or "").strip()
            val = parse_float(a.get(ac["value"]))
            if val is None:
                continue
            if nid == _ENERGY_KJ_ID:
                kj_energy[fid] = val
                continue
            field = _NUTRIENT_MAP.get(nid)
            if field:
                setattr(row, field, val)
        for fid, row in rows.items():
            if row.calories_per_100g is None and fid in kj_energy:
                row.calories_per_100g = kj_to_kcal(kj_energy[fid])
        return [normalise_row(r) for r in rows.values()]


SOURCE = _Cnf()
