import os
from typing import Dict, List

from scripts.build_food_db.model import NormalisedRow
from scripts.build_food_db.normalise import normalise_row
from scripts.build_food_db.sources.base import (
    Source, read_xlsx_rows, parse_float, kj_to_kcal,
)

# Australian Food Composition Database (FSANZ), Release 2. Ships as several
# .xlsx workbooks; the build joins the food-details workbook to the
# per-100g nutrient workbook on "Public Food Key". Energy is published in
# kJ only, so it is always converted with kj_to_kcal. Minerals are mg and
# vitamins ug already -> no g->mg/mcg conversion. Nutrient headers in the
# real files carry an embedded newline before the unit, e.g.
# "Protein \n(g)"; the constants below match that.
FILES = {
    "details": "Release2_Food_Details.xlsx",
    "nutrients": "Release2_Food_Nutrients_per_100g.xlsx",
}
SHEET_DETAILS = None
SHEET_NUTRIENTS = None
COLS = {
    "details": {
        "id": "Public Food Key",
        "name": "Food Name",
        "category": "Classification",
    },
    "nutrients": {
        "id": "Public Food Key",
        "energy_kj": "Energy with dietary fibre, equated \n(kJ)",
        "protein_g": "Protein \n(g)",
        "fat_g": "Total fat \n(g)",
        "carbs_g": "Available carbohydrate, with sugar alcohols \n(g)",
        "fibre_g": "Total dietary fibre \n(g)",
        "sugar_g": "Total sugars \n(g)",
        "sodium_mg": "Sodium (Na) \n(mg)",
        "calcium_mg": "Calcium (Ca) \n(mg)",
        "iron_mg": "Iron (Fe) \n(mg)",
        "vitamin_c_mg": "Vitamin C \n(mg)",
        "vitamin_d_mcg": "Vitamin D3 equivalents \n(µg)",
        "vitamin_b12_mcg": "Vitamin B12 \n(µg)",
    },
}


class _Afcd(Source):
    id = "afcd"

    def extract(self, raw_dir: str) -> List[NormalisedRow]:
        dc = COLS["details"]
        nc = COLS["nutrients"]
        rows: Dict[str, NormalisedRow] = {}
        for d in read_xlsx_rows(os.path.join(raw_dir, FILES["details"]),
                                SHEET_DETAILS):
            key = (d.get(dc["id"]) or "").strip()
            if not key:
                continue
            rows[key] = NormalisedRow(
                source_id="afcd", source_food_id=key,
                name=(d.get(dc["name"]) or "").strip(),
                category=(d.get(dc["category"]) or None),
            )
        for n in read_xlsx_rows(os.path.join(raw_dir, FILES["nutrients"]),
                                SHEET_NUTRIENTS):
            key = (n.get(nc["id"]) or "").strip()
            row = rows.get(key)
            if row is None:
                continue
            row.calories_per_100g = kj_to_kcal(parse_float(n.get(nc["energy_kj"])))
            row.protein_per_100g = parse_float(n.get(nc["protein_g"]))
            row.fat_per_100g = parse_float(n.get(nc["fat_g"]))
            row.carbs_per_100g = parse_float(n.get(nc["carbs_g"]))
            row.fiber_per_100g = parse_float(n.get(nc["fibre_g"]))
            row.sugar_per_100g = parse_float(n.get(nc["sugar_g"]))
            row.sodium_mg_per_100g = parse_float(n.get(nc["sodium_mg"]))
            row.calcium_mg_per_100g = parse_float(n.get(nc["calcium_mg"]))
            row.iron_mg_per_100g = parse_float(n.get(nc["iron_mg"]))
            row.vitamin_c_mg_per_100g = parse_float(n.get(nc["vitamin_c_mg"]))
            row.vitamin_d_mcg_per_100g = parse_float(n.get(nc["vitamin_d_mcg"]))
            row.vitamin_b12_mcg_per_100g = parse_float(n.get(nc["vitamin_b12_mcg"]))
        return [normalise_row(r) for r in rows.values()]


SOURCE = _Afcd()
