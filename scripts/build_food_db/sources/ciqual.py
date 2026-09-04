import os
from typing import List

from scripts.build_food_db.model import NormalisedRow
from scripts.build_food_db.normalise import normalise_row
from scripts.build_food_db.sources.base import (
    Source, read_xlsx_rows, parse_float, kj_to_kcal,
)

# France CIQUAL 2025 (ANSES). Single table shipped as .xls/.xlsx; re-save
# as .xlsx if openpyxl rejects the .xls. Values use French decimal commas
# and mark below-detection as "traces" / "-" / "< x" (handled by
# base.parse_float). Minerals are already mg/100 g and vitamins ug/100 g,
# so no g->mg/mcg conversion is needed; only kJ energy is converted, and
# only when the kcal column is blank.
FILE = "Table_Ciqual_2025.xlsx"
SHEET = None  # single-sheet workbook -> active sheet
COLS = {
    "id": "alim_code",
    "name": "alim_nom_fr",
    "category": "alim_grp_nom_fr",
    "energy_kj": "Energie, Règlement UE N° 1169/2011 (kJ/100 g)",
    "energy_kcal": "Energie, Règlement UE N° 1169/2011 (kcal/100 g)",
    "protein_g": "Protéines, N x facteur de Jones (g/100 g)",
    "fat_g": "Lipides (g/100 g)",
    "carbs_g": "Glucides (g/100 g)",
    "fibre_g": "Fibres alimentaires (g/100 g)",
    "sugar_g": "Sucres (g/100 g)",
    "sodium_mg": "Sodium (mg/100 g)",
    "calcium_mg": "Calcium (mg/100 g)",
    "iron_mg": "Fer (mg/100 g)",
    "vitamin_c_mg": "Vitamine C (mg/100 g)",
    "vitamin_d_mcg": "Vitamine D (µg/100 g)",
    "vitamin_b12_mcg": "Vitamine B12 (µg/100 g)",
}


class _Ciqual(Source):
    id = "ciqual"

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
                source_id="ciqual",
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


SOURCE = _Ciqual()
