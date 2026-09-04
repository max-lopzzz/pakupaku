import os
from typing import List

from scripts.build_food_db.model import NormalisedRow
from scripts.build_food_db.normalise import normalise_row
from scripts.build_food_db.sources.base import (
    Source, read_xlsx_rows, parse_float, kj_to_kcal,
)

# UK CoFID (McCance & Widdowson's Composition of Foods Integrated Dataset
# 2021). Published as a single .xlsx workbook, read directly like the other
# xlsx sources (ciqual / afcd / frida). CoFID already reports minerals in mg
# and vitamins in ug, so only energy needs converting (kJ -> kcal) and only
# when the kcal column is blank.
FILE = "McCance_Widdowsons_Composition_of_Foods_Integrated_Dataset_2021.xlsx"
# TODO(task 9): pin sheet + column names against the real McCance & Widdowson
# workbook — the published edition spreads nutrients over several sheets
# ("1.3 Proximates", "1.4 Inorganics", "1.5 Vitamins", ...). Open the
# workbook, find the sheet carrying the per-100g columns below, and re-pin
# both SHEET and COLS. Until then this is a best-guess sheet name.
SHEET = "1.3 Proximates"
COLS = {
    "id": "Food Code",
    "name": "Food Name",
    "category": "Group",
    "energy_kcal": "Energy (kcal) (kcal)",
    "energy_kj": "Energy (kJ) (kJ)",
    "protein_g": "Protein (g)",
    "fat_g": "Fat (g)",
    "carbs_g": "Carbohydrate (g)",
    "fibre_g": "AOAC fibre (g)",
    "sugar_g": "Total sugars (g)",
    "sodium_mg": "Sodium (mg)",
    "calcium_mg": "Calcium (mg)",
    "iron_mg": "Iron (mg)",
    "vitamin_c_mg": "Vitamin C (mg)",
    "vitamin_d_mcg": "Vitamin D (µg)",
    "vitamin_b12_mcg": "Vitamin B12 (µg)",
}


class _Cofid(Source):
    id = "cofid"

    def extract(self, raw_dir: str) -> List[NormalisedRow]:
        c = COLS
        rows: List[NormalisedRow] = []
        for r in read_xlsx_rows(os.path.join(raw_dir, FILE), SHEET):
            name = (r.get(c["name"]) or "").strip()
            if not name:
                continue
            kcal = parse_float(r.get(c["energy_kcal"]))
            if kcal is None:
                kcal = kj_to_kcal(parse_float(r.get(c["energy_kj"])))
            row = NormalisedRow(
                source_id="cofid",
                source_food_id=(r.get(c["id"]) or "").strip(),
                name=name,
                category=(r.get(c["category"]) or None),
                calories_per_100g=kcal,
                protein_per_100g=parse_float(r.get(c["protein_g"])),
                fat_per_100g=parse_float(r.get(c["fat_g"])),
                carbs_per_100g=parse_float(r.get(c["carbs_g"])),
                fiber_per_100g=parse_float(r.get(c["fibre_g"])),
                sugar_per_100g=parse_float(r.get(c["sugar_g"])),
                sodium_mg_per_100g=parse_float(r.get(c["sodium_mg"])),
                calcium_mg_per_100g=parse_float(r.get(c["calcium_mg"])),
                iron_mg_per_100g=parse_float(r.get(c["iron_mg"])),
                vitamin_c_mg_per_100g=parse_float(r.get(c["vitamin_c_mg"])),
                vitamin_d_mcg_per_100g=parse_float(r.get(c["vitamin_d_mcg"])),
                vitamin_b12_mcg_per_100g=parse_float(r.get(c["vitamin_b12_mcg"])),
            )
            rows.append(normalise_row(row))
        return rows


SOURCE = _Cofid()
