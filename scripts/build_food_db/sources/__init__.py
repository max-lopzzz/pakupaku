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
from scripts.build_food_db.sources.ciqual import SOURCE as CIQUAL
from scripts.build_food_db.sources.afcd import SOURCE as AFCD
from scripts.build_food_db.sources.cnf import SOURCE as CNF
from scripts.build_food_db.sources.frida import SOURCE as FRIDA

# Order matches the "Included sources" table in docs/food-data-sources.md.
ALL_SOURCES: List[Source] = [
    USDA,    # USDA FoodData Central (US) — public domain / CC0
    COFID,   # UK CoFID — Open Government Licence v3.0
    CIQUAL,  # France CIQUAL / ANSES — Licence Ouverte / Etalab 2.0
    AFCD,    # Australian Food Composition Database / FSANZ — CC BY-SA 3.0 AU
    CNF,     # Canadian Nutrient File / Health Canada — OGL – Canada
    FRIDA,   # Frida / DTU (Denmark) — free reuse with citation
]

SOURCES_BY_ID = {s.id: s for s in ALL_SOURCES}
