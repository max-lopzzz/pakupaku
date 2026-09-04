"""Write a tiny 2-row ``foods.sqlite`` artifact for seed_foods tests.

Uses the same DDL and column order as the offline build
(``scripts/build_food_db``) so the file is byte-for-byte shaped like a
real artifact, just smaller.
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
        ("gen:00002", "Water, tap, drinking", json.dumps(["Water, tap, drinking"]),
         None, "unspecified", 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 4.0, 3.0, 0.0, 0.0, None, None,
         json.dumps([]), json.dumps(["cofid", "usda"]), 2),
    ]
    ph = ",".join(["?"] * (8 + len(NUTRIENT_FIELDS)))
    con.executemany("INSERT INTO foods VALUES (%s)" % ph, rows)
    con.commit()
    con.close()


if __name__ == "__main__":
    build(sys.argv[1])
