import os

from scripts.build_food_db.sources.base import (
    to_mg, to_mcg, kj_to_kcal, read_xlsx_rows, parse_float,
)
from scripts.build_food_db.sources.usda import SOURCE as USDA
from scripts.build_food_db.sources.cofid import SOURCE as COFID
from scripts.build_food_db.sources.cnf import SOURCE as CNF
from scripts.build_food_db.sources.ciqual import SOURCE as CIQUAL

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


def test_parse_float_comma_is_decimal_only_for_short_fractions():
    # thousands separators are stripped, not treated as a decimal point
    assert parse_float("1,200") == 1200.0
    assert parse_float("1,234,567") == 1234567.0
    # a lone comma with <=2 trailing digits is a French/Danish decimal
    assert parse_float("1,2") == 1.2
    assert parse_float("12,34") == 12.34


def test_usda_extractor_reads_generic_rows_only(tmp_path):
    from tests.build_food_db.conftest import usda_raw_dir
    raw = usda_raw_dir(tmp_path)

    rows = USDA.extract(raw)

    by_name = {r.name: r for r in rows}
    assert "Water, tap, drinking" in by_name
    water = by_name["Water, tap, drinking"]
    assert water.source_id == "usda"
    assert water.calories_per_100g == 0.0
    # normalise_row already applied. "water" is a key stopword but it is the
    # head noun of "Water, tap, drinking" (end of the pre-comma segment), so
    # F12 keeps it; "tap" and "drinking" are ordinary tokens.
    assert water.canonical_key == "drinking tap water"
    assert water.prep_state == "unspecified"
    # branded / FNDDS rows from the slice are excluded
    assert all("BRANDED" not in r.name.upper() for r in rows)
    assert all("restaurant" not in r.name.lower() for r in rows)

    broccoli = by_name["Broccoli, raw"]
    assert broccoli.calories_per_100g == 34.0
    assert broccoli.canonical_key == "broccoli"
    assert broccoli.vitamin_c_mg_per_100g == 89.2


def test_cofid_extractor_reads_broccoli(tmp_path):
    from tests.build_food_db.conftest import cofid_raw_dir
    raw = cofid_raw_dir(tmp_path)

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


def test_read_xlsx_rows_maps_headers_to_dicts():
    path = os.path.join(FIX, "ciqual_slice.xlsx")
    rows = list(read_xlsx_rows(path, "Table Ciqual 2025"))
    assert len(rows) == 10
    first = rows[0]
    assert first["alim_nom_fr"] == "Brocoli, cru"
    assert first["alim_code"] == "20047"
    # blank/None cells come back as "" not KeyError
    assert first["Vitamine D (µg/100 g)"] == "0"


def test_ciqual_extractor_handles_french_decimals(tmp_path):
    from tests.build_food_db.conftest import single_file_raw_dir
    raw = single_file_raw_dir(tmp_path, "ciqual", "ciqual_slice.xlsx",
                              "Table_Ciqual_2025.xlsx")

    rows = CIQUAL.extract(raw)

    by_key = {r.canonical_key: r for r in rows}
    broc = by_key["brocoli cru"]
    assert broc.source_id == "ciqual"
    assert broc.source_food_id == "20047"
    assert broc.calories_per_100g == 34.3            # comma decimal parsed
    assert broc.protein_per_100g == 2.98
    assert broc.sodium_mg_per_100g == 8.52
    assert broc.vitamin_c_mg_per_100g == 89.2
    # Task-3 prep detection is English-only: French "cru" is not recognised
    assert broc.prep_state == "unspecified"

    apple = by_key["crue pomme"]
    assert apple.sodium_mg_per_100g is None          # "traces" -> None
    assert apple.vitamin_c_mg_per_100g == 4.6

    rice = by_key["blanc cru riz"]
    assert round(rice.calories_per_100g, 1) == 363.0   # kcal blank -> kJ/4.184


def test_afcd_extractor_joins_two_workbooks_and_converts_kj(tmp_path):
    from scripts.build_food_db.sources.afcd import SOURCE as AFCD
    from tests.build_food_db.conftest import afcd_raw_dir
    raw = afcd_raw_dir(tmp_path)

    rows = AFCD.extract(raw)

    by_key = {r.canonical_key: r for r in rows}
    broc = by_key["broccoli"]
    assert broc.source_id == "afcd"
    assert broc.source_food_id == "F001234"
    assert broc.calories_per_100g == round(141 / 4.184, 4)   # kJ -> kcal
    assert broc.protein_per_100g == 4.4
    assert broc.sodium_mg_per_100g == 7.0
    assert broc.vitamin_c_mg_per_100g == 84.0
    # F8: raw source category columns are no longer carried through
    assert broc.category is None
    assert broc.prep_state == "raw"


def test_frida_extractor_reads_xlsx(tmp_path):
    from scripts.build_food_db.sources.frida import SOURCE as FRIDA
    from tests.build_food_db.conftest import single_file_raw_dir
    raw = single_file_raw_dir(tmp_path, "frida", "frida_slice.xlsx",
                              "Frida_5.3.xlsx")

    rows = FRIDA.extract(raw)

    by_key = {r.canonical_key: r for r in rows}
    broc = by_key["broccoli"]
    assert broc.source_id == "frida"
    assert broc.source_food_id == "42"
    assert broc.calories_per_100g == 35.0
    assert broc.protein_per_100g == 3.4
    assert broc.sodium_mg_per_100g == 8.0
    assert broc.vitamin_c_mg_per_100g == 89.0
    assert broc.prep_state == "raw"

    chicken = by_key["breast chicken"]
    assert round(chicken.calories_per_100g, 1) == 164.9    # kcal blank -> kJ


def test_all_sources_registered_and_rejected_ones_absent():
    from scripts.build_food_db.sources import ALL_SOURCES, SOURCES_BY_ID

    ids = [s.id for s in ALL_SOURCES]
    assert ids == ["usda", "cofid", "ciqual", "afcd", "cnf", "frida"]
    assert len(ids) == len(set(ids)) == 6
    assert set(SOURCES_BY_ID) == set(ids)
    # every registered source exposes the Source.extract interface
    for s in ALL_SOURCES:
        assert callable(getattr(s, "extract", None))
    # the four licence-rejected regional sources have no module
    import importlib
    for missing in ("fao_regional", "korea"):
        try:
            importlib.import_module(
                "scripts.build_food_db.sources." + missing
            )
        except ModuleNotFoundError:
            continue
        raise AssertionError(missing + " should not exist")
