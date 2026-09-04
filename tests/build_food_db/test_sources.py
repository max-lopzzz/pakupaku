import os

from scripts.build_food_db.sources.base import to_mg, to_mcg, kj_to_kcal
from scripts.build_food_db.sources.usda import SOURCE as USDA
from scripts.build_food_db.sources.cofid import SOURCE as COFID
from scripts.build_food_db.sources.cnf import SOURCE as CNF

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def test_unit_helpers():
    assert to_mg(0.5) == 500.0          # 0.5 g -> mg
    assert to_mg(0.001) == 1.0          # 0.001 g -> 1 mg
    assert to_mcg(0.001) == 1000.0      # 0.001 g -> 1000 mcg
    assert to_mcg(0.000001) == 1.0      # 1e-6 g -> 1 mcg
    assert round(kj_to_kcal(1000.0), 1) == 239.0
    assert to_mg(None) is None
    assert to_mcg(None) is None
    assert kj_to_kcal(None) is None


def test_usda_extractor_reads_generic_rows_only(tmp_path):
    from tests.build_food_db.conftest import usda_raw_dir
    raw = usda_raw_dir(tmp_path)

    rows = USDA.extract(raw)

    by_name = {r.name: r for r in rows}
    assert "Water, tap, drinking" in by_name
    water = by_name["Water, tap, drinking"]
    assert water.source_id == "usda"
    assert water.calories_per_100g == 0.0
    # normalise_row already applied ("water" itself is a Task-3 key stopword)
    assert water.canonical_key == "drinking tap"
    assert water.prep_state == "unspecified"
    # branded / FNDDS rows from the slice are excluded
    assert all("BRANDED" not in r.name.upper() for r in rows)
    assert all("restaurant" not in r.name.lower() for r in rows)

    broccoli = by_name["Broccoli, raw"]
    assert broccoli.calories_per_100g == 34.0
    assert broccoli.canonical_key == "broccoli"
    assert broccoli.vitamin_c_mg_per_100g == 89.2


def test_cofid_extractor_reads_broccoli(tmp_path):
    from tests.build_food_db.conftest import single_file_raw_dir
    raw = single_file_raw_dir(tmp_path, "cofid", "cofid_slice.csv",
                              "cofid_2021.csv")

    rows = COFID.extract(raw)

    by_key = {r.canonical_key: r for r in rows}
    assert "broccoli" in by_key
    broc = by_key["broccoli"]
    assert broc.source_id == "cofid"
    assert broc.source_food_id == "13-001"
    assert broc.calories_per_100g == 33.0
    assert broc.protein_per_100g == 4.4
    assert broc.sodium_mg_per_100g == 8.0
    assert broc.vitamin_c_mg_per_100g == 87.0
    assert broc.prep_state == "raw"

    # energy falls back to kJ->kcal when the kcal column is blank
    chicken = by_key["breast chicken"]
    assert round(chicken.calories_per_100g, 1) == 156.1


def test_cnf_extractor_joins_amount_to_food_and_nutrient(tmp_path):
    from tests.build_food_db.conftest import cnf_raw_dir
    raw = cnf_raw_dir(tmp_path)

    rows = CNF.extract(raw)

    by_key = {r.canonical_key: r for r in rows}
    assert "broccoli" in by_key
    broc = by_key["broccoli"]
    assert broc.source_id == "cnf"
    assert broc.source_food_id == "2"
    assert broc.calories_per_100g == 34.0
    assert broc.protein_per_100g == 2.82
    assert broc.sodium_mg_per_100g == 33.0
    assert broc.vitamin_c_mg_per_100g == 89.2
    assert broc.vitamin_b12_mcg_per_100g == 0.0
    assert broc.prep_state == "raw"

    # chicken has no kcal row, only kJ -> converted
    chicken = by_key["breast chicken meat only"]
    assert round(chicken.calories_per_100g, 1) == 164.9
