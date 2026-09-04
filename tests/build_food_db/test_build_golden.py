import hashlib
import os
import shutil
import sqlite3

from scripts.build_food_db.model import NormalisedRow
from scripts.build_food_db.normalise import normalise_row
from scripts.build_food_db.build import build
from scripts.build_food_db.portions import load_fndds_portions
from scripts.build_food_db.sources.cofid import SOURCE as COFID

_MINI = os.path.join(os.path.dirname(__file__), "fixtures", "mini")


def _r(src, name, **nut):
    return normalise_row(NormalisedRow(source_id=src, source_food_id=src + name, name=name, **nut))


def test_build_produces_deterministic_foods_table(tmp_path):
    rows = [
        _r("usda", "Broccoli, raw", calories_per_100g=34.0, protein_per_100g=2.8),
        _r("cofid", "raw broccoli", calories_per_100g=33.0, protein_per_100g=3.0),
        _r("ciqual", "broccoli raw", calories_per_100g=35.0, protein_per_100g=2.9),
        _r("usda", "Water, tap, drinking", calories_per_100g=0.0),
        _r("cofid", "tap water", calories_per_100g=0.0),
    ]
    portions = {"broccoli": [{"unit": "cup chopped", "grams": 91.0}]}

    out = tmp_path / "foods.sqlite"
    build(rows, portions, {}, str(out))
    build(rows, portions, {}, str(out))     # twice: must be identical

    con = sqlite3.connect(str(out))
    got = con.execute(
        "SELECT id, canonical_name, prep_state, calories_per_100g, source_count, portions "
        "FROM foods ORDER BY id"
    ).fetchall()
    con.close()

    assert got == [
        ("gen:00001", "Broccoli, raw", "raw", 34.0, 3, '[{"unit": "cup chopped", "grams": 91.0}]'),
        ("gen:00002", "Water, tap, drinking", "unspecified", 0.0, 2, "[]"),
    ]


def test_build_raises_on_unresolved_conflict(tmp_path):
    rows = [
        _r("usda", "Broccoli, raw", calories_per_100g=34.0),
        _r("ciqual", "raw broccoli", calories_per_100g=400.0),
    ]
    import pytest
    with pytest.raises(ValueError):
        build(rows, {}, {}, str(tmp_path / "x.sqlite"))


def test_build_mini_end_to_end(tmp_path):
    """Drive the whole pipeline from real extractor input (fixtures/mini/)
    through matching, aggregation, portion attach and the SQLite write,
    and assert the artifact is byte-identical when rebuilt."""
    raw = tmp_path / "raw"
    (raw / "cofid").mkdir(parents=True)
    (raw / "usda").mkdir(parents=True)
    shutil.copy(os.path.join(_MINI, "cofid_2021.csv"), raw / "cofid" / "cofid_2021.csv")
    shutil.copy(os.path.join(_MINI, "usda", "food.csv"), raw / "usda" / "food.csv")
    shutil.copy(os.path.join(_MINI, "usda", "food_portion.csv"),
                raw / "usda" / "food_portion.csv")

    rows = COFID.extract(str(raw / "cofid"))
    portions = load_fndds_portions(str(raw))

    out = tmp_path / "foods.sqlite"
    build(rows, portions, {}, str(out))
    digest_1 = hashlib.sha256(out.read_bytes()).hexdigest()
    build(rows, portions, {}, str(out))
    digest_2 = hashlib.sha256(out.read_bytes()).hexdigest()
    print("\nmini build sha256 run 1:", digest_1)
    print("mini build sha256 run 2:", digest_2)
    assert digest_1 == digest_2, "rebuild is not byte-identical"

    con = sqlite3.connect(str(out))
    got = con.execute(
        "SELECT id, canonical_name, prep_state, calories_per_100g, source_count, "
        "aliases, portions FROM foods ORDER BY id"
    ).fetchall()
    con.close()

    assert got == [
        ("gen:00001", "raw broccoli", "raw", 34.0, 1,
         '["Broccoli, raw", "raw broccoli"]',
         '[{"unit": "cup chopped", "grams": 91.0}]'),
        ("gen:00002", "raw carrots", "raw", 36.0, 1,
         '["Carrots, raw", "raw carrots"]',
         '[{"unit": "cup chopped", "grams": 122.0}]'),
    ]
