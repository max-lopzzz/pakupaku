from sqlalchemy import select

import models
from seed_foods import seed_foods
from tests.fixtures.make_foods_mini import build as build_mini


async def test_seed_replaces_foods_table_from_artifact(db_session, tmp_path):
    art = tmp_path / "foods.sqlite"
    build_mini(str(art))
    n = await seed_foods(db_session, str(art))
    await db_session.commit()
    names = (await db_session.execute(
        select(models.Food.canonical_name).order_by(models.Food.id)
    )).scalars().all()
    assert n == 5
    assert names == [
        "Broccoli, raw", "Water, tap, drinking", "Coconut water",
        "Butter", "Butter beans, canned",
    ]


async def test_seed_missing_artifact_is_a_noop(db_session, tmp_path):
    assert await seed_foods(db_session, str(tmp_path / "nope.sqlite")) == 0
