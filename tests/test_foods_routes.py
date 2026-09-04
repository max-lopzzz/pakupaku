"""
tests/test_foods_routes.py
--------------------------
``GET /foods/search`` is served entirely from the in-memory
``food_index`` singleton. The ``@app.on_event("startup")`` hook that
normally primes it does NOT fire under this repo's ``client`` fixture
(``TestClient(app)`` with no ``with`` block), so each test seeds + loads
the index itself, then hits the route.
"""

import asyncio
import uuid

from auth import get_current_user, hash_password
from main import app
from models import User

import food_index
from seed_foods import seed_foods
from tests.fixtures.make_foods_mini import build as build_mini


async def _prime_index(db_session, tmp_path):
    art = tmp_path / "foods.sqlite"
    build_mini(str(art))
    await seed_foods(db_session, str(art))
    await db_session.commit()
    await food_index.load(db_session)


def _make_user():
    return User(
        id=uuid.uuid4(),
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        username=f"user{uuid.uuid4().hex[:8]}",
        hashed_password=hash_password("TestPass123!"),
        email_verified=True,
        safe_mode=False,
        uses_custom_goals=False,
        is_admin=False,
    )


def test_foods_search_returns_index_results(client, db_session, tmp_path):
    asyncio.get_event_loop().run_until_complete(_prime_index(db_session, tmp_path))
    app.dependency_overrides[get_current_user] = lambda: _make_user()
    try:
        r = client.get("/foods/search?query=broccoli")
        assert r.status_code == 200
        body = r.json()["foods"]
        assert body[0]["food_id"] == "gen:00001"
        assert body[0]["calories_per_100g"] == 34.0
        assert body[0]["portions"] == [{"unit": "cup chopped", "grams": 91.0}]
        assert "dataType" not in body[0] and "brandOwner" not in body[0]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_foods_search_empty_when_index_not_loaded(client, db_session):
    food_index._by_id.clear()
    food_index._by_key.clear()
    app.dependency_overrides[get_current_user] = lambda: _make_user()
    try:
        r = client.get("/foods/search?query=broccoli")
        assert r.status_code == 200
        assert r.json() == {"foods": []}
    finally:
        app.dependency_overrides.pop(get_current_user, None)
