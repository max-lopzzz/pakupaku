import itertools
import os
from typing import Dict, List

from scripts.build_food_db.model import NormalisedRow
from scripts.build_food_db.normalise import normalise_row
from scripts.build_food_db.sources.base import (
    Source, read_xlsx_rows, parse_float, kj_to_kcal, find_header,
)

# UK CoFID (McCance & Widdowson's Composition of Foods Integrated Dataset
# 2021, gov.uk). Nutrients are spread across three sheets, joined on the
# first column (labelled "Food Code" on most sheets, but a stray space on
# "1.4 Inorganics" — so the id column is read positionally, not by name).
# CoFID already reports minerals in mg and vitamins in ug, so only energy
# needs converting (kJ -> kcal), and only when the kcal column is blank.
FILE = "McCance_Widdowsons_Composition_of_Foods_Integrated_Dataset_2021.xlsx"
SHEET_PROXIMATES = "1.3 Proximates"
SHEET_INORGANICS = "1.4 Inorganics"
SHEET_VITAMINS = "1.5 Vitamins"


def _first_col(row: Dict[str, str]) -> str:
    return row.get("__col0__", "")


def _sheet_rows(raw_dir: str, sheet: str):
    rows_iter = read_xlsx_rows(os.path.join(raw_dir, FILE), sheet)
    try:
        first = next(rows_iter)
    except StopIteration:
        return None, iter(())
    return list(first.keys()), itertools.chain([first], rows_iter)


class _Cofid(Source):
    id = "cofid"

    def extract(self, raw_dir: str) -> List[NormalisedRow]:
        prox_headers, prox_rows = _sheet_rows(raw_dir, SHEET_PROXIMATES)
        if prox_headers is None:
            return []
        name_col = find_header(prox_headers, "food name")
        cat_col = find_header(prox_headers, "group")
        kcal_col = find_header(prox_headers, "energy", "kcal")
        kj_col = find_header(prox_headers, "energy", "kj")
        protein_col = find_header(prox_headers, "protein")
        fat_col = find_header(prox_headers, "fat")
        carbs_col = find_header(prox_headers, "carbohydrate")
        fibre_col = find_header(prox_headers, "aoac fibre")
        sugar_col = find_header(prox_headers, "total sugars")

        rows: Dict[str, NormalisedRow] = {}
        for r in prox_rows:
            fid = (_first_col(r) or "").strip()
            name = (r.get(name_col) or "").strip() if name_col else ""
            if not fid or not name:
                continue
            kcal = parse_float(r.get(kcal_col)) if kcal_col else None
            if kcal is None and kj_col:
                kcal = kj_to_kcal(parse_float(r.get(kj_col)))
            rows[fid] = NormalisedRow(
                source_id="cofid", source_food_id=fid, name=name,
                category=None,  # raw source categories aren't reconciled yet (Plan-2)
                calories_per_100g=kcal,
                protein_per_100g=parse_float(r.get(protein_col)) if protein_col else None,
                fat_per_100g=parse_float(r.get(fat_col)) if fat_col else None,
                carbs_per_100g=parse_float(r.get(carbs_col)) if carbs_col else None,
                fiber_per_100g=parse_float(r.get(fibre_col)) if fibre_col else None,
                sugar_per_100g=parse_float(r.get(sugar_col)) if sugar_col else None,
            )

        inorg_headers, inorg_rows = _sheet_rows(raw_dir, SHEET_INORGANICS)
        if inorg_headers is not None:
            sodium_col = find_header(inorg_headers, "sodium")
            calcium_col = find_header(inorg_headers, "calcium")
            iron_col = find_header(inorg_headers, "iron")
            for r in inorg_rows:
                fid = (_first_col(r) or "").strip()
                row = rows.get(fid)
                if row is None:
                    continue
                row.sodium_mg_per_100g = parse_float(r.get(sodium_col)) if sodium_col else None
                row.calcium_mg_per_100g = parse_float(r.get(calcium_col)) if calcium_col else None
                row.iron_mg_per_100g = parse_float(r.get(iron_col)) if iron_col else None

        vit_headers, vit_rows = _sheet_rows(raw_dir, SHEET_VITAMINS)
        if vit_headers is not None:
            vitc_col = find_header(vit_headers, "vitamin c")
            vitd_col = find_header(vit_headers, "vitamin d")
            vitb12_col = find_header(vit_headers, "vitamin b12")
            for r in vit_rows:
                fid = (_first_col(r) or "").strip()
                row = rows.get(fid)
                if row is None:
                    continue
                row.vitamin_c_mg_per_100g = parse_float(r.get(vitc_col)) if vitc_col else None
                row.vitamin_d_mcg_per_100g = parse_float(r.get(vitd_col)) if vitd_col else None
                row.vitamin_b12_mcg_per_100g = parse_float(r.get(vitb12_col)) if vitb12_col else None

        return [normalise_row(r) for r in rows.values()]


SOURCE = _Cofid()
