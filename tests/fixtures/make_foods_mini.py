"""Write a tiny ``foods.sqlite`` artifact for seed_foods / food_index tests.

Uses the same DDL and column order as the offline build
(``scripts/build_food_db``) so the file is byte-for-byte shaped like a
real artifact, just smaller.

``gen:00003``/``gen:00004``/``gen:00005`` (coconut water, butter, butter
beans) exist to exercise the fuzzy tie-break: ``token_set_ratio`` scores
100 for any candidate whose tokens are a subset of the query's, so
without the secondary re-rank ``best_match("butter beans")`` returns
plain ``Butter``. ``gen:00002``'s name ("Water, tap") matches the real
offline artifact's AFCD/Frida-derived naming (built from the actual
national tables, not a guess) — a longer synthetic "Water, tap, drinking"
was tried first and reintroduced the tie-break bug it was meant to guard
against, because the extra "drinking" token doesn't exist in any real
source's name. ``gen:00006`` ("Coconut milk (liquid from grated meat and water), canned"
— a real CNF-source alias name found in the built artifact) exists to
exercise the real bug found there: its canonical key's head noun happens
to be "water" (the last word before the first comma), so it scores a
perfect 100 ``token_set_ratio`` against the query "water" even though
"water" is one ingredient mention in an otherwise unrelated 8-token
product name — a one-word query must not resolve to it just because
``process.extract``'s tie order happens to favour it.
"""

import json
import sqlite3
import sys

from scripts.build_food_db.build import FOODS_TABLE_DDL
from scripts.build_food_db.model import NUTRIENT_FIELDS


def build(path):
    con = sqlite3.connect(path)
    con.execute(FOODS_TABLE_DDL)
    rows = [
        ("gen:00001", "Broccoli, raw", json.dumps(["Broccoli, raw", "raw broccoli"]),
         None, "raw", 34.0, 2.8, 0.4, 7.0, 2.6, 1.7, 33.0, 47.0, 0.7, 89.2, None, None,
         json.dumps([{"unit": "cup chopped", "grams": 91.0}]), json.dumps(["cofid", "usda"]), 2),
        ("gen:00002", "Water, tap", json.dumps(["Water, tap"]),
         None, "unspecified", 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 4.0, 3.0, 0.0, 0.0, None, None,
         json.dumps([]), json.dumps(["cofid", "usda"]), 2),
        ("gen:00003", "Coconut water", json.dumps(["Coconut water"]),
         None, "unspecified", 19.0, 0.7, 0.2, 3.7, 1.1, 2.6, 105.0, 24.0, 0.29, 2.4, None, None,
         json.dumps([]), json.dumps(["cofid", "usda"]), 2),
        ("gen:00004", "Butter", json.dumps(["Butter"]),
         None, "unspecified", 717.0, 0.85, 81.1, 0.06, 0.0, 0.06, 11.0, 24.0, 0.02, 0.0, 1.5, 0.17,
         json.dumps([]), json.dumps(["cofid", "usda"]), 2),
        ("gen:00005", "Butter beans, canned", json.dumps(["Butter beans, canned"]),
         None, "unspecified", 115.0, 7.3, 0.3, 20.0, 4.8, 1.5, 350.0, 35.0, 1.9, 0.0, None, None,
         json.dumps([]), json.dumps(["cofid", "usda"]), 2),
        ("gen:00006", "Coconut milk (liquid from grated meat and water), canned",
         json.dumps(["Coconut milk (liquid from grated meat and water), canned"]),
         None, "unspecified", 230.0, 2.3, 23.8, 5.5, 2.2, 3.3, 15.0, 16.0, 3.9, 2.8, None, None,
         json.dumps([]), json.dumps(["cnf", "usda"]), 2),
    ]
    ph = ",".join(["?"] * (8 + len(NUTRIENT_FIELDS)))
    con.executemany("INSERT INTO foods VALUES (%s)" % ph, rows)
    con.commit()
    con.close()


if __name__ == "__main__":
    build(sys.argv[1])
