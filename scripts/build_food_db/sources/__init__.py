"""Confirmed national / regional food-composition source extractors.

Only sources whose licence permits redistribution + commercial use +
attribution are wired in here — see ``docs/food-data-sources.md``. The
four rejected regional sources (FAO West Africa, FAO Central & Eastern
Africa, FAO ASEAN, South Korea RDA) have no extractor.
"""

from typing import List

from scripts.build_food_db.sources.base import Source
from scripts.build_food_db.sources.usda import SOURCE as USDA

ALL_SOURCES: List[Source] = [
    USDA,
]
