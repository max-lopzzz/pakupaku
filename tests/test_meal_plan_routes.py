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


from datetime import date, timedelta
from models import FoodLog


def _generate(client, u, db_session, days=1, meals=3):
    loop = asyncio.get_event_loop()
    for name, kcal, mt in [
        ("Oats", 450, "breakfast"), ("Toast", 400, "breakfast"),
        ("Salad", 650, "lunch"), ("Wrap", 600, "lunch"),
        ("Curry", 700, "dinner"), ("Stew", 680, "dinner"),
    ]:
        loop.run_until_complete(_recipe(db_session, u, name=name, kcal=kcal, mt=mt))
    loop.run_until_complete(db_session.commit())
    return client.post("/meal-plan/generate",
                       json={"days": days, "meals_per_day": meals, "diet_tags": []}).json()


def test_swap_replaces_a_single_entry(client, db_session):
    loop = asyncio.get_event_loop()
    u = loop.run_until_complete(_user(db_session))
    c = _as(client, u)
    body = _generate(c, u, db_session)
    lunch = [e for e in body["plan_days"][0]["entries"] if e["slot"] == "lunch"][0]
    old_recipe_id = lunch["recipe"]["id"]

    res = c.post("/meal-plan/entries/%s/swap" % lunch["id"])
    assert res.status_code == 200
    swapped = res.json()
    assert swapped["entry"]["slot"] == "lunch"
    assert swapped["entry"]["recipe"]["id"] != old_recipe_id
    assert "calories" in swapped["day_totals"]


def test_swap_404_for_another_users_entry(client, db_session):
    loop = asyncio.get_event_loop()
    u1 = loop.run_until_complete(_user(db_session))
    u2 = loop.run_until_complete(_user(db_session))
    body = _generate(_as(client, u1), u1, db_session)
    entry_id = body["plan_days"][0]["entries"][0]["id"]
    _as(client, u2)
    assert client.post("/meal-plan/entries/%s/swap" % entry_id).status_code == 404
    app.dependency_overrides.pop(get_current_user, None)


def test_swap_409_when_no_alternative(client, db_session):
    loop = asyncio.get_event_loop()
    u = loop.run_until_complete(_user(db_session))
    # exactly one breakfast recipe -> nothing to swap it for
    loop.run_until_complete(_recipe(db_session, u, name="Only Oats", kcal=450, mt="breakfast"))
    loop.run_until_complete(_recipe(db_session, u, name="Lunch A", kcal=650, mt="lunch"))
    loop.run_until_complete(_recipe(db_session, u, name="Dinner A", kcal=700, mt="dinner"))
    loop.run_until_complete(db_session.commit())
    c = _as(client, u)
    body = c.post("/meal-plan/generate", json={"days": 1, "meals_per_day": 3, "diet_tags": []}).json()
    bfast = [e for e in body["plan_days"][0]["entries"] if e["slot"] == "breakfast"][0]
    assert c.post("/meal-plan/entries/%s/swap" % bfast["id"]).status_code == 409
    app.dependency_overrides.pop(get_current_user, None)


def test_day_log_creates_food_logs_then_409_then_force(client, db_session):
    loop = asyncio.get_event_loop()
    u = loop.run_until_complete(_user(db_session))
    c = _as(client, u)
    _generate(c, u, db_session, days=2, meals=3)

    res = c.post("/meal-plan/days/1/log", json={})
    assert res.status_code == 200
    assert res.json()["created"] == 3
    logs = loop.run_until_complete(db_session.execute(
        FoodLog.__table__.select().where(FoodLog.user_id == u.id))).fetchall()
    assert len(logs) == 3
    assert all(row.log_date == date.today() + timedelta(days=1) for row in logs)
    assert {row.meal for row in logs} == {"breakfast", "lunch", "dinner"}

    assert c.post("/meal-plan/days/1/log", json={}).status_code == 409
    assert c.post("/meal-plan/days/1/log", json={"force": True}).status_code == 200
    logs2 = loop.run_until_complete(db_session.execute(
        FoodLog.__table__.select().where(FoodLog.user_id == u.id))).fetchall()
    assert len(logs2) == 6

    app.dependency_overrides.pop(get_current_user, None)


def test_day_log_404_for_out_of_range_day(client, db_session):
    loop = asyncio.get_event_loop()
    u = loop.run_until_complete(_user(db_session))
    c = _as(client, u)
    _generate(c, u, db_session, days=1, meals=3)
    assert c.post("/meal-plan/days/5/log", json={}).status_code == 404
    app.dependency_overrides.pop(get_current_user, None)
