"""Confirmed national / regional food-composition source extractors.

Only sources whose licence permits redistribution + commercial use +
attribution are wired in here — see ``docs/food-data-sources.md``. The
four rejected regional sources (FAO West Africa, FAO Central & Eastern
Africa, FAO ASEAN, South Korea RDA) have no extractor.
"""

from typing import List

from scripts.build_food_db.sources.base import Source
from scripts.build_food_db.sources.usda import SOURCE as USDA
from scripts.build_food_db.sources.cofid import SOURCE as COFID
from scripts.build_food_db.sources.cnf import SOURCE as CNF
from scripts.build_food_db.sources.ciqual import SOURCE as CIQUAL
from scripts.build_food_db.sources.afcd import SOURCE as AFCD
from scripts.build_food_db.sources.frida import SOURCE as FRIDA

ALL_SOURCES: List[Source] = [
    USDA,
    COFID,
    CNF,
    CIQUAL,
    AFCD,
    FRIDA,
]
