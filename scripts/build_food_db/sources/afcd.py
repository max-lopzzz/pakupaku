import itertools
import os
from typing import Dict, List

from scripts.build_food_db.model import NormalisedRow
from scripts.build_food_db.normalise import normalise_row
from scripts.build_food_db.sources.base import (
    Source, read_xlsx_rows, parse_float, kj_to_kcal, find_header,
)

# Australian Food Composition Database (FSANZ), Release 3. Ships as several
# .xlsx workbooks, each with a "Contents" cover sheet plus the real data
# sheet; the real data starts on row 3 (row 1 is a title, row 2 is blank).
# The build joins the food-details workbook to the per-100g nutrient
# workbook on "Public Food Key". Energy is published in kJ only, so it is
# always converted with kj_to_kcal. Minerals are mg and vitamins ug
# already -> no g->mg/mcg conversion. Nutrient headers in the real files
# carry an embedded newline before the unit, e.g. "Protein \n(g)"; columns
# are located with find_header() (normalised substring match) rather than
# exact strings, since exact punctuation/units drift across releases.
FILES = {
    "details": "AFCD Release 3 - Food Details.xlsx",
    "nutrients": "AFCD Release 3 - Nutrient profiles.xlsx",
}
SHEET_DETAILS = "Food details"
SHEET_NUTRIENTS = "All solids & liquids per 100 g"
HEADER_ROW = 3


def _rows_with_headers(path: str, sheet: str):
    rows_iter = read_xlsx_rows(path, sheet, header_row=HEADER_ROW)
    try:
        first = next(rows_iter)
    except StopIteration:
        return None, iter(())
    return list(first.keys()), itertools.chain([first], rows_iter)


class _Afcd(Source):
    id = "afcd"

    def extract(self, raw_dir: str) -> List[NormalisedRow]:
        d_headers, d_rows = _rows_with_headers(
            os.path.join(raw_dir, FILES["details"]), SHEET_DETAILS)
        if d_headers is None:
            return []
        id_col = find_header(d_headers, "public food key")
        name_col = find_header(d_headers, "food name")

        rows: Dict[str, NormalisedRow] = {}
        for d in d_rows:
            key = (d.get(id_col) or "").strip() if id_col else ""
            if not key:
                continue
            rows[key] = NormalisedRow(
                source_id="afcd", source_food_id=key,
                name=(d.get(name_col) or "").strip() if name_col else "",
                category=None,  # raw source categories aren't reconciled yet (Plan-2)
            )

        n_headers, n_rows = _rows_with_headers(
            os.path.join(raw_dir, FILES["nutrients"]), SHEET_NUTRIENTS)
        if n_headers is not None:
            nid_col = find_header(n_headers, "public food key")
            energy_kj_col = find_header(n_headers, "energy with dietary fibre")
            protein_col = find_header(n_headers, "protein", exclude="nitrogen")
            fat_col = find_header(n_headers, "fat, total") or find_header(n_headers, "total fat")
            carbs_col = find_header(n_headers, "available carbohydrate, with sugar alcohols")
            fibre_col = find_header(n_headers, "total dietary fibre")
            sugar_col = find_header(n_headers, "total sugars")
            sodium_col = find_header(n_headers, "sodium (na)")
            calcium_col = find_header(n_headers, "calcium (ca)")
            iron_col = find_header(n_headers, "iron (fe)")
            vitc_col = find_header(n_headers, "vitamin c")
            vitd_col = find_header(n_headers, "vitamin d3 equivalents")
            vitb12_col = find_header(n_headers, "cobalamin")

            for n in n_rows:
                key = (n.get(nid_col) or "").strip() if nid_col else ""
                row = rows.get(key)
                if row is None:
                    continue
                row.calories_per_100g = kj_to_kcal(parse_float(n.get(energy_kj_col))) if energy_kj_col else None
                row.protein_per_100g = parse_float(n.get(protein_col)) if protein_col else None
                row.fat_per_100g = parse_float(n.get(fat_col)) if fat_col else None
                row.carbs_per_100g = parse_float(n.get(carbs_col)) if carbs_col else None
                row.fiber_per_100g = parse_float(n.get(fibre_col)) if fibre_col else None
                row.sugar_per_100g = parse_float(n.get(sugar_col)) if sugar_col else None
                row.sodium_mg_per_100g = parse_float(n.get(sodium_col)) if sodium_col else None
                row.calcium_mg_per_100g = parse_float(n.get(calcium_col)) if calcium_col else None
                row.iron_mg_per_100g = parse_float(n.get(iron_col)) if iron_col else None
                row.vitamin_c_mg_per_100g = parse_float(n.get(vitc_col)) if vitc_col else None
                row.vitamin_d_mcg_per_100g = parse_float(n.get(vitd_col)) if vitd_col else None
                row.vitamin_b12_mcg_per_100g = parse_float(n.get(vitb12_col)) if vitb12_col else None

        return [normalise_row(r) for r in rows.values()]


SOURCE = _Afcd()
