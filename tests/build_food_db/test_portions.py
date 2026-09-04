import os
import shutil

from scripts.build_food_db.aggregate import AggregatedFood
from scripts.build_food_db.normalise import canonical_key
from scripts.build_food_db.portions import attach_portions, load_fndds_portions

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def _food(name):
    return AggregatedFood(canonical_name=name, prep_state="raw", category=None,
                          source_ids=["usda", "cofid"], source_count=2,
                          calories_per_100g=1.0)


def test_exact_key_match_attaches_portions():
    portions = {"rice white": [{"unit": "cup", "grams": 186.0}]}
    out = attach_portions([_food("White rice")], portions)
    assert out[0][1] == [{"unit": "cup", "grams": 186.0}]


def test_no_match_yields_empty_portions():
    out = attach_portions([_food("Obscure gourd")], {"rice white": [{"unit": "cup", "grams": 186.0}]})
    assert out[0][1] == []


def _fndds_raw(tmp_path):
    """Lay out raw/usda/{food.csv,food_portion.csv} from the committed slices."""
    usda = tmp_path / "usda"
    usda.mkdir()
    shutil.copy(os.path.join(FIX, "fndds_food_slice.csv"), usda / "food.csv")
    shutil.copy(os.path.join(FIX, "fndds_portions_slice.csv"), usda / "food_portion.csv")
    return str(tmp_path)


def test_load_fndds_portions_divides_gram_weight_by_amount(tmp_path):
    portions = load_fndds_portions(_fndds_raw(tmp_path))
    # "amount=3, modifier=oz, gram_weight=85" -> 85 / 3 == 28.33 g per oz
    chicken = portions[canonical_key(
        "Chicken, broilers or fryers, breast, meat only, roasted")]
    assert {"unit": "oz", "grams": 28.33} in chicken


def test_load_fndds_portions_keeps_gram_weight_when_amount_blank(tmp_path):
    portions = load_fndds_portions(_fndds_raw(tmp_path))
    broc = portions[canonical_key("Broccoli, raw")]
    assert {"unit": "cup", "grams": 154.0} in broc


def test_load_fndds_portions_excludes_branded_descriptions(tmp_path):
    portions = load_fndds_portions(_fndds_raw(tmp_path))
    # fdc 1009 / 1010 are branded_food -> filtered out before name-keying
    assert canonical_key("SUPER CRUNCH BRANDED CEREAL") not in portions
    assert canonical_key("MEGA LOAF BRANDED BREAD") not in portions


def test_load_fndds_portions_includes_survey_fndds_rows(tmp_path):
    portions = load_fndds_portions(_fndds_raw(tmp_path))
    # survey_fndds_food is kept here (portions legitimately come from survey rows)
    assert canonical_key("Rice, white, cooked") in portions
