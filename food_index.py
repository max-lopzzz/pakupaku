"""
food_index.py
-------------
In-memory exact / alias / fuzzy search + match index over the ``foods``
table (built offline by ``scripts/build_food_db`` and loaded into the
runtime DB by ``seed_foods``).

``load`` is called once at startup with a live ``AsyncSession`` and again
after any re-seed — it is idempotent and clears prior state first.
``search`` / ``best_match`` are plain sync functions over the module
singletons, so request handlers never touch the DB for a lookup.
"""

import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from rapidfuzz import fuzz, process
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from scripts.build_food_db.normalise import canonical_key
from models import Food as FoodRow

MATCH_CONFIDENCE_FLOOR = 60

_NUTRIENTS = (
    "calories_per_100g", "protein_per_100g", "fat_per_100g", "carbs_per_100g",
    "fiber_per_100g", "sugar_per_100g", "sodium_mg_per_100g", "calcium_mg_per_100g",
    "iron_mg_per_100g", "vitamin_c_mg_per_100g", "vitamin_d_mcg_per_100g",
    "vitamin_b12_mcg_per_100g",
)


@dataclass
class Food:
    id: str
    description: str
    prep_state: str
    portions: List[Dict[str, float]] = field(default_factory=list)
    calories_per_100g: Optional[float] = None
    protein_per_100g: Optional[float] = None
    fat_per_100g: Optional[float] = None
    carbs_per_100g: Optional[float] = None
    fiber_per_100g: Optional[float] = None
    sugar_per_100g: Optional[float] = None
    sodium_mg_per_100g: Optional[float] = None
    calcium_mg_per_100g: Optional[float] = None
    iron_mg_per_100g: Optional[float] = None
    vitamin_c_mg_per_100g: Optional[float] = None
    vitamin_d_mcg_per_100g: Optional[float] = None
    vitamin_b12_mcg_per_100g: Optional[float] = None

    def _nutrients(self) -> Dict[str, Optional[float]]:
        return {n: getattr(self, n) for n in _NUTRIENTS}

    def as_search_result(self) -> Dict:
        out = {"food_id": self.id, "description": self.description, "portions": self.portions}
        out.update(self._nutrients())
        return out

    def as_detail(self) -> Dict:
        return self.as_search_result()


_by_id: Dict[str, Food] = {}
_by_key: Dict[str, List[Food]] = {}
_keys: List[str] = []


def _loaded() -> bool:
    return bool(_by_id)


async def load(session: AsyncSession) -> None:
    """Rebuild the index from every ``foods`` row on ``session``.

    Idempotent: clears ``_by_id`` / ``_by_key`` first, so it is safe to
    call again after a re-seed.
    """
    global _keys
    _by_id.clear()
    _by_key.clear()
    rows = (await session.execute(select(FoodRow))).scalars().all()
    for r in rows:
        f = Food(
            id=r.id, description=r.canonical_name, prep_state=r.prep_state,
            portions=json.loads(r.portions or "[]"),
            **{n: getattr(r, n) for n in _NUTRIENTS},
        )
        _by_id[f.id] = f
        names = [r.canonical_name] + json.loads(r.aliases or "[]")
        for name in names:
            _by_key.setdefault(canonical_key(name), []).append(f)
    _keys = list(_by_key)


def _ranked(query: str, limit: int) -> List[Food]:
    key = canonical_key(query)
    seen = set()
    out: List[Food] = []

    def _add(foods):
        for f in foods:
            if f.id not in seen:
                seen.add(f.id)
                out.append(f)

    if key in _by_key:
        _add(_by_key[key])
    for cand, score, _ in process.extract(
        key, _keys, scorer=fuzz.token_set_ratio, limit=limit * 3
    ):
        if score < MATCH_CONFIDENCE_FLOOR:
            break
        _add(_by_key[cand])
    return out[:limit]


def search(query: str, limit: int = 25) -> List[Food]:
    if not _loaded() or not query.strip():
        return []
    return _ranked(query, limit)


def best_match(name: str) -> Optional[Food]:
    hits = search(name, 1)
    return hits[0] if hits else None


def get(food_id: str) -> Optional[Food]:
    return _by_id.get(food_id)


def reset() -> None:
    """Drop all loaded state — for tests, and for a fresh re-load."""
    global _keys
    _by_id.clear()
    _by_key.clear()
    _keys.clear()
