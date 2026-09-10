"""Meal-plan generation engine. See docs/superpowers/specs/2026-09-10-meal-planner-design.md."""

from sqlalchemy.ext.asyncio import AsyncSession


async def backfill_meal_types(session: AsyncSession) -> int:
    """Replaced in Task 2."""
    return 0
