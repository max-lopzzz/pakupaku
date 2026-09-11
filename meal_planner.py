"""Meal-plan generation engine. See docs/superpowers/specs/2026-09-10-meal-planner-design.md."""

import random
import re
from dataclasses import dataclass
from typing import Dict, FrozenSet, List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models import Recipe

# Multi-word / unambiguous keys stay plain substring checks.
_BREAKFAST_KEYWORDS = (
    "overnight", "pancake", "waffle", "smoothie", "granola",
    "porridge", "cereal", "chia pudding", "french toast", "breakfast",
)
_SNACK_KEYWORDS = (
    "bites", "bliss ball", "energy ball", "crackers", "snack",
)
# Short, ambiguous keys: whole-word match only, so "oat" doesn't fire on
# "Goat Cheese Salad", "toast" on "Toasted Sesame Noodles", or "dip" on
# "Chicken Dippers". The \bbar\b here replaces the old trailing-space "bar " hack.
_BREAKFAST_WORD_RE = re.compile(r"\b(oat|oats|toast)\b")
_SNACK_WORD_RE = re.compile(r"\b(dip|bark|bar)\b")
_SNACK_KCAL_CEILING = 200.0


def infer_meal_type(name: str, kcal: Optional[float]) -> str:
    n = (name or "").lower()
    if any(k in n for k in _BREAKFAST_KEYWORDS) or _BREAKFAST_WORD_RE.search(n):
        return "breakfast"
    if any(k in n for k in _SNACK_KEYWORDS) or _SNACK_WORD_RE.search(n):
        return "snack"
    if isinstance(kcal, (int, float)) and kcal <= _SNACK_KCAL_CEILING:
        return "snack"
    return "any"


async def backfill_meal_types(session: AsyncSession) -> int:
    rows = (await session.execute(
        select(Recipe.id, Recipe.name, Recipe.total_calories).where(Recipe.meal_type.is_(None))
    )).all()
    for rid, name, kcal in rows:
        await session.execute(
            update(Recipe).where(Recipe.id == rid).values(meal_type=infer_meal_type(name, kcal))
        )
    return len(rows)


SLOT_ORDER = ["breakfast", "lunch", "dinner", "snack"]
_SLOT_WEIGHTS = {"breakfast": 0.25, "lunch": 0.35, "dinner": 0.35, "snack": 0.05}
_SERVINGS_MIN, _SERVINGS_MAX = 0.5, 2.5
_SNACK_ANY_KCAL_CEILING = 250.0
_SCORE_W = {"kcal": 1.0, "protein_g": 0.6, "carbs_g": 0.3, "fat_g": 0.3}
_DUP_PENALTY = 0.5
_RECENT_PENALTY = 0.15


@dataclass(frozen=True)
class RecipeOption:
    id: str
    name: str
    meal_type: str
    diet_tags: FrozenSet[str]
    kcal: float
    protein_g: float
    fat_g: float
    carbs_g: float
    fiber_g: float


@dataclass
class PlannedEntry:
    slot: str
    option: Optional[RecipeOption]
    servings: float
    kcal: float
    protein_g: float
    fat_g: float
    carbs_g: float
    fiber_g: float

    @property
    def unfilled(self) -> bool:
        return self.option is None


@dataclass
class PlannedDay:
    entries: List[PlannedEntry]
    totals: Dict[str, float]
    score: float


def active_slots(meals_per_day: int) -> List[str]:
    return SLOT_ORDER[:meals_per_day]


def slot_budgets(day_target_kcal: float, slots: List[str]) -> Dict[str, float]:
    total_w = sum(_SLOT_WEIGHTS[s] for s in slots)
    return {s: day_target_kcal * (_SLOT_WEIGHTS[s] / total_w) for s in slots}


def build_buckets(options, diet_tags: FrozenSet[str], slots: List[str]) -> Dict[str, List[RecipeOption]]:
    eligible = [o for o in options
               if diet_tags <= o.diet_tags and isinstance(o.kcal, (int, float)) and o.kcal > 0]
    buckets: Dict[str, List[RecipeOption]] = {s: [] for s in slots}
    for o in eligible:
        for s in slots:
            if s == "snack":
                if o.meal_type == "snack" or (o.meal_type == "any" and o.kcal <= _SNACK_ANY_KCAL_CEILING):
                    buckets[s].append(o)
            else:
                if o.meal_type == s or o.meal_type == "any":
                    buckets[s].append(o)
    return buckets


def _scaled_entry(slot: str, option: Optional[RecipeOption], budget: float) -> PlannedEntry:
    if option is None:
        return PlannedEntry(slot, None, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    servings = min(max(budget / option.kcal, _SERVINGS_MIN), _SERVINGS_MAX)
    servings = round(servings, 2)
    return PlannedEntry(
        slot, option, servings,
        round(option.kcal * servings, 2),
        round(option.protein_g * servings, 2),
        round(option.fat_g * servings, 2),
        round(option.carbs_g * servings, 2),
        round(option.fiber_g * servings, 2),
    )


def _rel_err(actual: float, target: Optional[float]) -> float:
    if not isinstance(target, (int, float)) or target <= 0:
        return 0.0
    return abs(actual - target) / target


def _day_totals(entries: List[PlannedEntry]) -> Dict[str, float]:
    return {k: round(sum(getattr(e, k) for e in entries), 2)
            for k in ("kcal", "protein_g", "fat_g", "carbs_g", "fiber_g")}


def _score(entries, totals, day_target, recent_recipe_ids: FrozenSet[str]) -> float:
    s = 0.0
    for key in ("kcal", "protein_g", "fat_g", "carbs_g"):
        tgt = day_target.get(key)
        w = _SCORE_W[key]
        if key == "kcal":
            unfilled_penalty = sum(1.0 for e in entries if e.unfilled)
            s += w * (_rel_err(totals["kcal"], tgt) + unfilled_penalty)
        else:
            s += w * _rel_err(totals[key], tgt)
    ids = [e.option.id for e in entries if e.option is not None]
    s += _DUP_PENALTY * (len(ids) - len(set(ids)))
    s += _RECENT_PENALTY * len(set(ids) & recent_recipe_ids)
    return s


def plan_day(buckets, day_target, budgets, recent_recipe_ids: FrozenSet[str],
             rng: random.Random, n: int = 400) -> PlannedDay:
    slots = list(budgets.keys())
    best: Optional[PlannedDay] = None
    for _ in range(n):
        entries = []
        for slot in slots:
            bucket = buckets.get(slot) or []
            option = rng.choice(bucket) if bucket else None
            entries.append(_scaled_entry(slot, option, budgets[slot]))
        totals = _day_totals(entries)
        sc = _score(entries, totals, day_target, recent_recipe_ids)
        if best is None or sc < best.score:
            best = PlannedDay(entries, totals, sc)
    return best


def generate_plan(options, days: int, meals_per_day: int, targets, diet_tags: FrozenSet[str],
                  seed: Optional[int] = None, n: int = 400) -> List[PlannedDay]:
    rng = random.Random(seed)
    slots = active_slots(meals_per_day)
    budgets = slot_budgets(targets["kcal"], slots)
    buckets = build_buckets(options, diet_tags, slots)
    day_target = {"kcal": targets["kcal"], "protein_g": targets.get("protein_g"),
                  "fat_g": targets.get("fat_g"), "carbs_g": targets.get("carbs_g")}
    plan: List[PlannedDay] = []
    recent: FrozenSet[str] = frozenset()
    for _ in range(days):
        day = plan_day(buckets, day_target, budgets, recent, rng, n=n)
        plan.append(day)
        recent = frozenset(e.option.id for e in day.entries if e.option is not None)
    return plan


def swap_entry(options, day_entries, slot: str, budgets, day_target, diet_tags: FrozenSet[str],
               exclude_recipe_id: Optional[str], seed: Optional[int] = None,
               n: int = 400) -> Optional[PlannedEntry]:
    rng = random.Random(seed)
    slots = list(budgets.keys())
    bucket = [o for o in build_buckets(options, diet_tags, slots).get(slot, [])
              if o.id != exclude_recipe_id]
    if not bucket:
        return None
    others = [e for e in day_entries if e.slot != slot]
    best_entry: Optional[PlannedEntry] = None
    best_score = None
    for _ in range(n):
        cand = _scaled_entry(slot, rng.choice(bucket), budgets[slot])
        entries = others + [cand]
        totals = _day_totals(entries)
        sc = _score(entries, totals, day_target, frozenset())
        if best_score is None or sc < best_score:
            best_score, best_entry = sc, cand
    return best_entry
