import asyncio
import json
import uuid

from auth import get_current_user, hash_password
from main import app
from models import MealPlan, Recipe, User


async def _user(db_session, *, kcal=2000.0, protein=120.0, fat=65.0, carbs=220.0, custom=False):
    u = User(
        id=uuid.uuid4(), email=f"{uuid.uuid4()}@e.com", username=uuid.uuid4().hex[:8],
        hashed_password=hash_password("x"), email_verified=True, safe_mode=False,
        uses_custom_goals=custom, is_admin=False,
    )
    if custom:
        u.custom_kcal, u.custom_protein, u.custom_fat, u.custom_carbs = kcal, protein, fat, carbs
    else:
        u.target_kcal, u.protein_g, u.fat_g, u.carbs_g = kcal, protein, fat, carbs
    db_session.add(u)
    await db_session.flush()
    return u


async def _recipe(db_session, user, *, name, kcal, mt="any", shared=True, tags=None,
                  p=25.0, f=20.0, c=60.0):
    r = Recipe(
        id=uuid.uuid4(), user_id=user.id, name=name, servings=1.0, is_shared=shared,
        meal_type=mt, diet_tags=(",".join(tags) if tags else None),
        total_calories=kcal, total_protein_g=p, total_fat_g=f, total_carbs_g=c, total_fiber_g=6.0,
    )
    db_session.add(r)
    await db_session.flush()
    return r


def _as(client, user):
    app.dependency_overrides[get_current_user] = lambda: user
    return client


def test_generate_422_without_calorie_target(client, db_session):
    u = asyncio.get_event_loop().run_until_complete(_user(db_session, kcal=None))
    try:
        res = _as(client, u).post("/meal-plan/generate", json={"days": 2, "meals_per_day": 3, "diet_tags": []})
        assert res.status_code == 422
        assert "onboarding" in res.json()["detail"].lower()
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_generate_422_when_no_recipes_match_filters(client, db_session):
    loop = asyncio.get_event_loop()
    u = loop.run_until_complete(_user(db_session))
    loop.run_until_complete(_recipe(db_session, u, name="Meat Stew", kcal=600, tags=None))
    loop.run_until_complete(db_session.commit())
    try:
        res = _as(client, u).post("/meal-plan/generate",
                                  json={"days": 1, "meals_per_day": 3, "diet_tags": ["vegan"]})
        assert res.status_code == 422
        assert "no recipes" in res.json()["detail"].lower()
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_generate_get_and_regenerate_replaces(client, db_session):
    loop = asyncio.get_event_loop()
    u = loop.run_until_complete(_user(db_session))
    for i, (name, kcal, mt) in enumerate([
        ("Oats", 450, "breakfast"), ("Salad", 650, "lunch"),
        ("Curry", 700, "dinner"), ("Stew", 680, "dinner"), ("Bowl", 600, "any"),
    ]):
        loop.run_until_complete(_recipe(db_session, u, name=name, kcal=kcal, mt=mt))
    loop.run_until_complete(db_session.commit())
    try:
        c = _as(client, u)
        res = c.post("/meal-plan/generate", json={"days": 2, "meals_per_day": 3, "diet_tags": []})
        assert res.status_code == 200
        body = res.json()
        assert body["days"] == 2 and len(body["plan_days"]) == 2
        assert len(body["plan_days"][0]["entries"]) == 3
        assert body["targets"]["kcal"] == 2000.0
        first_id = body["id"]

        got = c.get("/meal-plan").json()
        assert got["id"] == first_id

        res2 = c.post("/meal-plan/generate", json={"days": 1, "meals_per_day": 2, "diet_tags": []})
        assert res2.status_code == 200
        assert res2.json()["id"] != first_id
        plans = loop.run_until_complete(db_session.execute(MealPlan.__table__.select())).fetchall()
        assert len(plans) == 1
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_get_meal_plan_null_when_none(client, db_session):
    u = asyncio.get_event_loop().run_until_complete(_user(db_session))
    try:
        assert _as(client, u).get("/meal-plan").json() is None
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_delete_meal_plan(client, db_session):
    loop = asyncio.get_event_loop()
    u = loop.run_until_complete(_user(db_session))
    for name, kcal, mt in [("Oats", 450, "breakfast"), ("Salad", 650, "lunch"), ("Curry", 700, "dinner")]:
        loop.run_until_complete(_recipe(db_session, u, name=name, kcal=kcal, mt=mt))
    loop.run_until_complete(db_session.commit())
    try:
        c = _as(client, u)
        assert c.post("/meal-plan/generate", json={"days": 1, "meals_per_day": 3, "diet_tags": []}).status_code == 200
        assert c.delete("/meal-plan").status_code == 204
        assert c.get("/meal-plan").json() is None
        assert c.delete("/meal-plan").status_code == 404
    finally:
        app.dependency_overrides.pop(get_current_user, None)
