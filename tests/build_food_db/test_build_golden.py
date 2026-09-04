import hashlib
import os
import shutil
import sqlite3

import pytest

from scripts.build_food_db.model import NormalisedRow
from scripts.build_food_db.normalise import normalise_row
from scripts.build_food_db import build as build_mod
from scripts.build_food_db.build import build, main
from scripts.build_food_db.portions import load_fndds_portions
from scripts.build_food_db.sources.cofid import SOURCE as COFID

_MINI = os.path.join(os.path.dirname(__file__), "fixtures", "mini")

# same 17 columns as fixtures/mini/cofid_2021.csv; 400 kcal disagrees with the
# 33/35 kcal broccoli rows, so the broccoli group stops auto-accepting.
_CONFLICTING_COFID_ROW = (
    '13-003,"broccoli, raw","Conflicting duplicate row",AR,'
    "400,1674,4.5,0.9,1.9,2.7,1.5,8,57,1.7,88,0,0\n"
)


def _mini_root(tmp_path, extra_cofid_rows=""):
    """Lay out a build root (``raw/<source_id>/`` + ``review/``) from the
    committed mini fixture and return it as a str."""
    root = tmp_path / "pkg"
    (root / "raw" / "cofid").mkdir(parents=True)
    (root / "raw" / "usda").mkdir(parents=True)
    (root / "review").mkdir()

    with open(os.path.join(_MINI, "cofid_2021.csv"), encoding="utf-8") as fh:
        cofid_csv = fh.read()
    if not cofid_csv.endswith("\n"):
        cofid_csv += "\n"
    (root / "raw" / "cofid" / "cofid_2021.csv").write_text(
        cofid_csv + extra_cofid_rows, encoding="utf-8")

    shutil.copy(os.path.join(_MINI, "usda", "food.csv"),
                root / "raw" / "usda" / "food.csv")
    shutil.copy(os.path.join(_MINI, "usda", "food_portion.csv"),
                root / "raw" / "usda" / "food_portion.csv")
    (root / "review" / "decisions.csv").write_text(
        "group_id,decision,canonical_name,note\n", encoding="utf-8")
    return root


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


def test_main_gives_each_extractor_its_own_raw_source_dir(tmp_path, monkeypatch):
    """main() must hand every source ``raw/<source_id>/``, not the raw root —
    extractors join their own filename onto the dir they are given."""
    monkeypatch.setattr(build_mod, "ALL_SOURCES", [COFID])
    root = _mini_root(tmp_path)
    out = tmp_path / "foods.sqlite"

    main(root=str(root), out_path=str(out))

    assert out.exists()
    con = sqlite3.connect(str(out))
    try:
        con.execute("SELECT id, canonical_name FROM foods").fetchall()
    finally:
        con.close()
    assert (root / "review" / "conflicts.csv").exists()


def test_main_exits_with_the_unresolved_conflict_count(tmp_path, monkeypatch):
    monkeypatch.setattr(build_mod, "ALL_SOURCES", [COFID])
    root = _mini_root(tmp_path, extra_cofid_rows=_CONFLICTING_COFID_ROW)
    out = tmp_path / "foods.sqlite"

    with pytest.raises(SystemExit) as excinfo:
        main(root=str(root), out_path=str(out))

    assert "1 unresolved merge conflicts" in str(excinfo.value)
    assert not out.exists()
    # conflicts.csv is regenerated before the build bails out
    conflicts = (root / "review" / "conflicts.csv").read_text(encoding="utf-8")
    assert "broccoli__raw" in conflicts
    assert "400" in conflicts
