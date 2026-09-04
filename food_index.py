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

    Idempotent and failure-atomic: the new maps are built into locals and
    only swapped into the module globals once every row has been read, so
    a malformed row raising mid-build leaves the previously loaded index
    intact rather than half-rebuilt (which ``_ranked`` could ``KeyError``
    on).
    """
    global _by_id, _by_key, _keys
    by_id: Dict[str, Food] = {}
    by_key: Dict[str, List[Food]] = {}
    rows = (await session.execute(select(FoodRow))).scalars().all()
    for r in rows:
        f = Food(
            id=r.id, description=r.canonical_name, prep_state=r.prep_state,
            portions=json.loads(r.portions or "[]"),
            **{n: getattr(r, n) for n in _NUTRIENTS},
        )
        by_id[f.id] = f
        names = [r.canonical_name] + json.loads(r.aliases or "[]")
        for name in names:
            by_key.setdefault(canonical_key(name), []).append(f)
    _by_id, _by_key, _keys = by_id, by_key, list(by_key)


def _ranked(query: str, limit: int) -> List[Food]:
    key = canonical_key(query)
    query_tokens = set(key.split())
    seen = set()
    out: List[Food] = []

    def _add(foods):
        for f in foods:
            if f.id not in seen:
                seen.add(f.id)
                out.append(f)

    # 1. Exact canonical-key hit(s) pinned first, in load order.
    if key in _by_key:
        _add(_by_key[key])

    # 2. Fuzzy candidates. ``token_set_ratio`` scores 100 for *any* candidate
    #    whose tokens are a subset of the query's (or vice versa), so
    #    "butter" ties "butter beans, canned" for query "butter beans", and a
    #    long unrelated name that merely *mentions* the query word (e.g.
    #    "canned coconut ... and water" for query "water") also ties at 100.
    #    Re-rank: a candidate only counts as "covers_all" when it covers
    #    every query token *and* doesn't drag in more than a couple of extra
    #    ones (real qualifiers like "tap"/"bottled" are fine; a whole other
    #    dish's worth of extra tokens is not) — within that group, fewer
    #    extra tokens wins, tied by ``token_sort_ratio``. Everything else
    #    (including covers_all candidates that failed the extra-token cap)
    #    is ranked purely by ``token_sort_ratio``, which penalises length
    #    mismatches in both directions instead of token_set_ratio's blind
    #    spot for short-candidate / long-candidate inflation.
    EXTRA_TOKEN_CAP = 2
    covers_all: List = []  # (cand_key, extra_count, sort_score)
    partial: List = []     # (cand_key, sort_score)
    # A real multi-thousand-food index routinely has dozens of candidates
    # tied at the ceiling set_score for a short query ("water", "milk", ...)
    # — retrieve a wide-enough pool that the re-rank below actually sees all
    # of them, not just whichever few process.extract's internal tie order
    # happened to keep when the caller only wants the single best match.
    retrieve_n = max(limit * 3, 200)
    for cand, set_score, _ in process.extract(
        key, _keys, scorer=fuzz.token_set_ratio, limit=retrieve_n
    ):
        if set_score < MATCH_CONFIDENCE_FLOOR:
            break  # process.extract yields descending set_score
        cand_tokens = set(cand.split())
        sort_score = fuzz.token_sort_ratio(key, cand)
        extra = len(cand_tokens - query_tokens)
        if query_tokens <= cand_tokens and extra <= EXTRA_TOKEN_CAP:
            covers_all.append((cand, extra, sort_score))
        else:
            partial.append((cand, sort_score))
    covers_all.sort(key=lambda t: (t[1], -t[2]))
    partial.sort(key=lambda t: -t[1])

    for cand, _, _ in covers_all:
        _add(_by_key.get(cand, []))
    for cand, _ in partial:
        _add(_by_key.get(cand, []))
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
