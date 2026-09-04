import os
from typing import List

from scripts.build_food_db.model import NormalisedRow
from scripts.build_food_db.normalise import normalise_row
from scripts.build_food_db.sources.base import (
    Source, read_xlsx_rows, parse_float, kj_to_kcal,
)

# Frida, the Danish Food Composition Database (DTU), version 5.3. Single
# downloadable spreadsheet with a per-100g data sheet. Frida publishes
# energy in both kcal and kJ; the kcal column is used directly, falling
# back to kJ -> kcal. Minerals are mg and vitamins ug already, so no
# g->mg/mcg conversion is required.
FILE = "Frida_5.3.xlsx"
SHEET = None
COLS = {
    "id": "FoodID",
    "name": "FoodName",
    "category": "FoodGroup",
    "energy_kcal": "Energy (kcal)",
    "energy_kj": "Energy (kJ)",
    "protein_g": "Protein (g)",
    "fat_g": "Fat (g)",
    "carbs_g": "Carbohydrate (g)",
    "fibre_g": "Dietary fibre (g)",
    "sugar_g": "Sugars (g)",
    "sodium_mg": "Sodium (mg)",
    "calcium_mg": "Calcium (mg)",
    "iron_mg": "Iron (mg)",
    "vitamin_c_mg": "Vitamin C (mg)",
    "vitamin_d_mcg": "Vitamin D (µg)",
    "vitamin_b12_mcg": "Vitamin B-12 (µg)",
}


class _Frida(Source):
    id = "frida"

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
                source_id="frida",
                source_food_id=(r.get(c["id"]) or "").strip(),
                name=name,
                category=None,  # raw source categories aren't reconciled yet (Plan-2)
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


SOURCE = _Frida()
