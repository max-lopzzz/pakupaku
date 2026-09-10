"""Meal-plan generation engine. See docs/superpowers/specs/2026-09-10-meal-planner-design.md."""

from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models import Recipe

_BREAKFAST_KEYWORDS = (
    "oat", "oats", "overnight", "pancake", "waffle", "smoothie", "granola",
    "toast", "porridge", "cereal", "chia pudding", "french toast", "breakfast",
)
_SNACK_KEYWORDS = (
    "bites", "bliss ball", "energy ball", "bark", "crackers", "dip", "snack", "bar ",
)
_SNACK_KCAL_CEILING = 200.0


def infer_meal_type(name: str, kcal: Optional[float]) -> str:
    n = (name or "").lower()
    if any(k in n for k in _BREAKFAST_KEYWORDS):
        return "breakfast"
    if any(k in n for k in _SNACK_KEYWORDS):
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
