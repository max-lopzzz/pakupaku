import os
from typing import Dict, List

from scripts.build_food_db.model import NormalisedRow
from scripts.build_food_db.normalise import normalise_row
from scripts.build_food_db.sources.base import Source, read_xlsx_rows, parse_float, kj_to_kcal

# Frida, the Danish Food Composition Database (DTU / National Food
# Institute), version 6.1 (data.dtu.dk, DOI 10.11583/DTU.32312844). Ships as
# a relational workbook rather than one flat per-100g sheet: "Data_Normalised"
# is a long table of (FoodID, ParameterID, ResVal) rows, one per
# food/nutrient pair, already expressed per 100 g in each parameter's own
# unit (see the "Parameter" sheet's Unit column) — so no g->mg/mcg scaling
# is needed. FoodName on each row is already the English name, so no
# separate join to the "Food" sheet is required for what this build uses.
FILE = "Frida_6.1.xlsx"
SHEET = "Data_Normalised"
COLS = {
    "food_id": "FoodID",
    "name": "FoodName",
    "parameter_id": "ParameterID",
    "value": "ResVal",
}
# Frida ParameterID -> NormalisedRow field, resolved against the real
# "Parameter" sheet (English ParameterName -> ParameterID) in version 6.1.
# 137 (Energy, kJ) is used only as a fallback when 356 (kcal) is absent.
_PARAMETER_MAP = {
    "356": "calories_per_100g",
    "218": "protein_per_100g",
    "141": "fat_per_100g",
    "170": "carbs_per_100g",     # Carbohydrate by difference (matches USDA/CNF convention)
    "168": "fiber_per_100g",
    "245": "sugar_per_100g",     # Sum sugars
    "201": "sodium_mg_per_100g",
    "108": "calcium_mg_per_100g",
    "162": "iron_mg_per_100g",
    "47": "vitamin_c_mg_per_100g",
    "126": "vitamin_d_mcg_per_100g",
    "38": "vitamin_b12_mcg_per_100g",
}
_ENERGY_KJ_ID = "137"


class _Frida(Source):
    id = "frida"

    def extract(self, raw_dir: str) -> List[NormalisedRow]:
        c = COLS
        rows: Dict[str, NormalisedRow] = {}
        kj_energy: Dict[str, float] = {}
        for r in read_xlsx_rows(os.path.join(raw_dir, FILE), SHEET):
            fid = (r.get(c["food_id"]) or "").strip()
            if not fid:
                continue
            row = rows.get(fid)
            if row is None:
                name = (r.get(c["name"]) or "").strip()
                if not name:
                    continue
                row = NormalisedRow(
                    source_id="frida", source_food_id=fid, name=name,
                    category=None,  # raw source categories aren't reconciled yet (Plan-2)
                )
                rows[fid] = row
            pid = (r.get(c["parameter_id"]) or "").strip()
            val = parse_float(r.get(c["value"]))
            if val is None:
                continue
            if pid == _ENERGY_KJ_ID:
                kj_energy[fid] = val
                continue
            field = _PARAMETER_MAP.get(pid)
            if field:
                setattr(row, field, val)
        for fid, row in rows.items():
            if row.calories_per_100g is None and fid in kj_energy:
                row.calories_per_100g = kj_to_kcal(kj_energy[fid])
        return [normalise_row(r) for r in rows.values()]


SOURCE = _Frida()
