"""
shared_recipe_maintenance.py
----------------------------
Housekeeping for the admin-curated shared recipe library:

- ``filter_unseen`` / ``shared_source_urls`` — used at bulk-import time so a
  re-run of the same blog doesn't create a second copy of every recipe.
- ``dedupe_shared_recipes`` — one-shot cleanup of the copies that already
  piled up before the dedupe guard existed.
- ``backfill_shared_images`` — re-fetch ``og:image`` for shared recipes
  that were saved (by an older frontend) with no image.

Every function takes a live ``AsyncSession``; the caller owns the commit.
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Sequence, Set, Tuple

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models import FoodLog, Recipe, RecipeIngredient
from recipe_import import _og_image, fetch_page

logger = logging.getLogger(__name__)

_DELETE_CHUNK = 100
_MIN_DT = datetime.min   # created_at is stored naive (datetime.utcnow)


def norm_url(u) -> str:
    """Loose URL key for duplicate detection — trailing slash and case are
    not meaningful for a recipe-post URL."""
    return (u or "").strip().rstrip("/").lower()


def _has_image(r: Recipe) -> bool:
    return bool((r.image_url or "").strip())


def _imageless_shared_with_source():
    return (
        Recipe.is_shared.is_(True),
        or_(Recipe.image_url.is_(None), Recipe.image_url == ""),
        Recipe.source_url.is_not(None),
    )


async def shared_source_urls(session: AsyncSession) -> Set[str]:
    rows = (await session.execute(
        select(Recipe.source_url).where(
            Recipe.is_shared.is_(True), Recipe.source_url.is_not(None)
        )
    )).scalars().all()
    return {norm_url(u) for u in rows if u}


def filter_unseen(candidate_urls: Sequence[str], seen: Set[str]) -> Tuple[List[str], int]:
    """Drop candidate URLs already saved as a shared recipe. Returns
    ``(kept, skipped_count)``."""
    kept = [u for u in candidate_urls if norm_url(u) not in seen]
    return kept, len(candidate_urls) - len(kept)


async def dedupe_shared_recipes(session: AsyncSession) -> Dict[str, int]:
    """Collapse shared recipes that share a source URL (or, lacking one, a
    name) down to a single keeper — preferring a copy that has an image,
    then the earliest-created. Deletes the rest (their ingredients cascade;
    any food_logs pointing at them are nulled)."""
    rows = (await session.execute(
        select(Recipe).where(Recipe.is_shared.is_(True))
    )).scalars().all()

    groups: Dict[str, List[Recipe]] = {}
    for r in rows:
        key = norm_url(r.source_url) or ("name:" + (r.name or "").strip().lower())
        groups.setdefault(key, []).append(r)

    delete_ids = []
    for members in groups.values():
        if len(members) < 2:
            continue
        members.sort(key=lambda r: (not _has_image(r), r.created_at or _MIN_DT))
        delete_ids.extend(m.id for m in members[1:])

    for i in range(0, len(delete_ids), _DELETE_CHUNK):
        chunk = delete_ids[i:i + _DELETE_CHUNK]
        await session.execute(
            update(FoodLog).where(FoodLog.recipe_id.in_(chunk)).values(recipe_id=None)
        )
        await session.execute(
            delete(RecipeIngredient).where(RecipeIngredient.recipe_id.in_(chunk))
        )
        await session.execute(delete(Recipe).where(Recipe.id.in_(chunk)))

    return {
        "shared_total": len(rows),
        "groups": len(groups),
        "deleted": len(delete_ids),
        "kept": len(rows) - len(delete_ids),
    }


async def backfill_shared_images(
    session: AsyncSession, limit: int = 40, concurrency: int = 5
) -> Dict[str, int]:
    """For up to ``limit`` shared recipes with a source URL but no image,
    fetch the page and pull its ``og:image``. Best-effort — a page that
    won't load or has no og:image is left as-is. Call repeatedly until
    ``remaining`` is 0."""
    rows = (await session.execute(
        select(Recipe).where(*_imageless_shared_with_source()).limit(limit)
    )).scalars().all()

    sem = asyncio.Semaphore(concurrency)

    async def _one(r: Recipe) -> int:
        async with sem:
            try:
                html = await fetch_page(r.source_url)
            except Exception:
                logger.warning("backfill: fetch failed for %s", r.source_url)
                return 0
        img = _og_image(html)
        if img:
            r.image_url = img
            return 1
        return 0

    updated = sum(await asyncio.gather(*[_one(r) for r in rows])) if rows else 0
    if updated:
        await session.flush()

    remaining = (await session.execute(
        select(func.count()).select_from(Recipe).where(*_imageless_shared_with_source())
    )).scalar_one()

    return {"checked": len(rows), "updated": updated, "remaining": int(remaining)}
