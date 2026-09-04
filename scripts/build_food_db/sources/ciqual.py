import itertools
import os
from typing import List

from scripts.build_food_db.model import NormalisedRow
from scripts.build_food_db.normalise import normalise_row
from scripts.build_food_db.sources.base import (
    Source, read_xlsx_rows, parse_float, kj_to_kcal, find_header,
)

# France CIQUAL 2025 (ANSES, via entrepot.recherche.data.gouv.fr). Single
# table shipped as .xlsx, sheet "composition nutritionnelle". Values use
# French decimal commas and mark below-detection as "traces" / "-" / "< x"
# (handled by base.parse_float). Minerals are already mg/100 g and vitamins
# ug/100 g, so no g->mg/mcg conversion is needed; only kJ energy is
# converted, and only when the kcal column is blank. Headers wrap across
# multiple lines in the real workbook, so columns are located by
# find_header() (normalised substring match) rather than exact strings.
FILE = "Table_Ciqual_2025.xlsx"
SHEET = "composition nutritionnelle"


def _locate(headers):
    return {
        "id": find_header(headers, "alim_code"),
        "name": find_header(headers, "alim_nom_fr"),
        "category": find_header(headers, "alim_grp_nom_fr"),
        "energy_kj": find_header(headers, "energie", "1169", "kj"),
        "energy_kcal": find_header(headers, "energie", "1169", "kcal"),
        "protein_g": find_header(headers, "proteines", "jones") or find_header(headers, "protéines", "jones"),
        "fat_g": find_header(headers, "lipides"),
        "carbs_g": find_header(headers, "glucides"),
        "fibre_g": find_header(headers, "fibres", "alimentaires"),
        "sugar_g": find_header(headers, "sucres"),
        "sodium_mg": find_header(headers, "sodium", exclude="chlorure"),
        "calcium_mg": find_header(headers, "calcium"),
        "iron_mg": find_header(headers, "fer ("),
        "vitamin_c_mg": find_header(headers, "vitamine", "c (mg"),
        "vitamin_d_mcg": find_header(headers, "vitamine", "d (") ,
        "vitamin_b12_mcg": find_header(headers, "vitamine", "b12"),
    }


class _Ciqual(Source):
    id = "ciqual"

    def extract(self, raw_dir: str) -> List[NormalisedRow]:
        rows_iter = read_xlsx_rows(os.path.join(raw_dir, FILE), SHEET)
        try:
            first = next(rows_iter)
        except StopIteration:
            return []
        c = _locate(list(first.keys()))
        rows: List[NormalisedRow] = []
        for r in itertools.chain([first], rows_iter):
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


SOURCE = _Ciqual()
