import os
from typing import Dict, List, Tuple

from rapidfuzz import fuzz, process

from scripts.build_food_db.aggregate import AggregatedFood
from scripts.build_food_db.normalise import canonical_key
from scripts.build_food_db.sources.base import read_csv_rows, parse_float

PORTION_MATCH_THRESHOLD = 90
# portion names come from FNDDS survey rows too, so — unlike usda.py's stricter
# nutrient filter — survey_fndds_food is kept here. branded_food descriptions
# are excluded so they aren't fuzzy-match candidates (and the dict isn't ~2M rows).
_PORTION_NAME_TYPES = {"foundation_food", "sr_legacy_food", "survey_fndds_food"}


def load_fndds_portions(raw_dir: str) -> Dict[str, List[Dict[str, float]]]:
    usda = os.path.join(raw_dir, "usda")
    # portion file: columns (fdc_id, portion_description / modifier, amount,
    # gram_weight). food file already copied by the USDA extractor step; re-read
    # for names, restricted to generic + survey rows.
    names: Dict[str, str] = {
        r["fdc_id"]: r["description"]
        for r in read_csv_rows(os.path.join(usda, "food.csv"))
        if r.get("data_type") in _PORTION_NAME_TYPES
    }
    out: Dict[str, List[Dict[str, float]]] = {}
    for r in read_csv_rows(os.path.join(usda, "food_portion.csv")):
        fid = r["fdc_id"]
        if fid not in names:
            continue
        unit = (r.get("portion_description") or r.get("modifier") or "").strip().lower()
        grams = parse_float(r.get("gram_weight"))
        if not unit or grams is None:
            continue
        # gram_weight is the mass of `amount` units, not of one unit
        # (amount=3, modifier="oz", gram_weight=85 -> 28.33 g per oz). Divide
        # when amount is a real multiplier; blank / 0 / 1 mean "one unit".
        amount = parse_float(r.get("amount"))
        if amount is not None and amount > 0 and amount != 1:
            grams = grams / amount
        key = canonical_key(names[fid])
        out.setdefault(key, [])
        if not any(p["unit"] == unit for p in out[key]):
            out[key].append({"unit": unit, "grams": round(grams, 2)})
    for key in out:
        out[key].sort(key=lambda p: p["unit"])
    return out


def attach_portions(foods: List[AggregatedFood],
                    portions: Dict[str, List[Dict[str, float]]]
                    ) -> List[Tuple[AggregatedFood, List[Dict[str, float]]]]:
    keys = list(portions)
    result = []
    for food in foods:
        k = canonical_key(food.canonical_name)
        if k in portions:
            result.append((food, portions[k]))
            continue
        match = process.extractOne(k, keys, scorer=fuzz.token_set_ratio,
                                   score_cutoff=PORTION_MATCH_THRESHOLD)
        result.append((food, portions[match[0]] if match else []))
    return result
