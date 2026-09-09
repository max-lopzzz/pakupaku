import uuid
from datetime import datetime, timedelta

import pytest

import shared_recipe_maintenance as srm
from auth import hash_password
from models import FoodLog, Recipe, RecipeIngredient, User
from shared_recipe_maintenance import (
    backfill_shared_images,
    dedupe_shared_recipes,
    filter_unseen,
    norm_url,
    shared_source_urls,
)


async def _user(db_session):
    u = User(
        id=uuid.uuid4(), email=f"{uuid.uuid4()}@e.com", username=uuid.uuid4().hex[:8],
        hashed_password=hash_password("x"), email_verified=True, safe_mode=False,
        uses_custom_goals=False, is_admin=True,
    )
    db_session.add(u)
    await db_session.flush()
    return u


async def _recipe(db_session, user, *, name, source_url=None, image_url=None,
                  created_at=None, ingredients=0):
    r = Recipe(
        id=uuid.uuid4(), user_id=user.id, name=name, servings=1.0, is_shared=True,
        source_url=source_url, image_url=image_url,
        created_at=created_at or datetime.utcnow(),
    )
    db_session.add(r)
    await db_session.flush()
    for i in range(ingredients):
        db_session.add(RecipeIngredient(
            id=uuid.uuid4(), recipe_id=r.id, food_name=f"ing{i}", amount_g=100.0,
        ))
    await db_session.flush()
    return r


def test_norm_url():
    assert norm_url("https://x.com/Recipe/") == "https://x.com/recipe"
    assert norm_url(" https://x.com/a ") == "https://x.com/a"
    assert norm_url(None) == ""


def test_filter_unseen():
    seen = {"https://x.com/a"}
    kept, skipped = filter_unseen(
        ["https://x.com/a/", "https://x.com/b", "https://x.com/A"], seen
    )
    assert kept == ["https://x.com/b"]
    assert skipped == 2


async def test_dedupe_keeps_image_copy_then_earliest(db_session):
    u = await _user(db_session)
    t0 = datetime(2026, 1, 1)
    # three copies of the same source; only the last has an image
    await _recipe(db_session, u, name="A", source_url="https://x.com/a", created_at=t0, ingredients=2)
    await _recipe(db_session, u, name="A", source_url="https://x.com/a/", created_at=t0 + timedelta(days=1), ingredients=2)
    keeper_img = await _recipe(db_session, u, name="A", source_url="https://x.com/a",
                               image_url="https://img/a.jpg", created_at=t0 + timedelta(days=2), ingredients=2)
    # a lone recipe — untouched
    solo = await _recipe(db_session, u, name="B", source_url="https://x.com/b")
    await db_session.commit()

    result = await dedupe_shared_recipes(db_session)
    await db_session.commit()

    assert result["deleted"] == 2
    assert result["kept"] == 2
    left = (await db_session.execute(
        Recipe.__table__.select().where(Recipe.is_shared == True)  # noqa: E712
    )).fetchall()
    left_ids = {row.id for row in left}
    assert left_ids == {keeper_img.id, solo.id}
    # deleted recipes' ingredients are gone too
    ing = (await db_session.execute(RecipeIngredient.__table__.select())).fetchall()
    assert {row.recipe_id for row in ing} <= left_ids


async def test_dedupe_nulls_food_logs_pointing_at_deleted_recipes(db_session):
    u = await _user(db_session)
    r1 = await _recipe(db_session, u, name="A", source_url="https://x.com/a", created_at=datetime(2026, 1, 1))
    r2 = await _recipe(db_session, u, name="A", source_url="https://x.com/a", created_at=datetime(2026, 1, 2))
    db_session.add(FoodLog(
        id=uuid.uuid4(), user_id=u.id, log_date=datetime(2026, 1, 3).date(),
        recipe_id=r2.id, food_name="A", amount_g=100.0, meal="lunch",
    ))
    await db_session.commit()

    await dedupe_shared_recipes(db_session)
    await db_session.commit()

    logs = (await db_session.execute(FoodLog.__table__.select())).fetchall()
    assert len(logs) == 1
    assert logs[0].recipe_id in (None, r1.id)  # r2 was deleted -> nulled (SET NULL) or kept if r1 was the deleted one


async def test_backfill_fills_og_image_and_reports_remaining(db_session, monkeypatch):
    u = await _user(db_session)
    await _recipe(db_session, u, name="no img 1", source_url="https://x.com/1")
    await _recipe(db_session, u, name="no img 2", source_url="https://x.com/2")
    await _recipe(db_session, u, name="no src",   source_url=None)
    await _recipe(db_session, u, name="has img",  source_url="https://x.com/3", image_url="https://img/3.jpg")
    await db_session.commit()

    async def fake_fetch(url):
        return f'<meta property="og:image" content="{url}/hero.jpg">'

    monkeypatch.setattr(srm, "fetch_page", fake_fetch)

    result = await backfill_shared_images(db_session, limit=1)
    await db_session.commit()
    assert result["checked"] == 1
    assert result["updated"] == 1
    assert result["remaining"] == 1   # the second source-having imageless recipe

    result = await backfill_shared_images(db_session, limit=10)
    await db_session.commit()
    assert result["updated"] == 1
    assert result["remaining"] == 0

    rows = (await db_session.execute(Recipe.__table__.select())).fetchall()
    by_name = {r.name: r.image_url for r in rows}
    assert by_name["no img 1"] == "https://x.com/1/hero.jpg"
    assert by_name["no img 2"] == "https://x.com/2/hero.jpg"
    assert by_name["no src"] is None
    assert by_name["has img"] == "https://img/3.jpg"


async def test_backfill_tolerates_a_failing_fetch(db_session, monkeypatch):
    u = await _user(db_session)
    await _recipe(db_session, u, name="bad", source_url="https://x.com/bad")

    async def boom(url):
        raise RuntimeError("network")

    monkeypatch.setattr(srm, "fetch_page", boom)
    result = await backfill_shared_images(db_session, limit=10)
    assert result["updated"] == 0
    assert result["remaining"] == 1
