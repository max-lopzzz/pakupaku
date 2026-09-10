import uuid

from meal_planner import backfill_meal_types, infer_meal_type
from models import Recipe, User
from auth import hash_password


def test_infer_meal_type_breakfast_keywords():
    assert infer_meal_type("Blueberry Overnight Oats", 350) == "breakfast"
    assert infer_meal_type("Fluffy Buttermilk Pancakes", 500) == "breakfast"
    assert infer_meal_type("Green Smoothie", 180) == "breakfast"


def test_infer_meal_type_snack_by_keyword_or_low_kcal():
    assert infer_meal_type("Cookie Dough Bliss Balls", 90) == "snack"
    assert infer_meal_type("Seeded Crackers", 400) == "snack"       # keyword wins over kcal
    assert infer_meal_type("Mystery Dish", 150) == "snack"          # low kcal, no keyword
    assert infer_meal_type("Mystery Dish", None) == "any"           # no kcal, no keyword


def test_infer_meal_type_default_any():
    assert infer_meal_type("Lentil Ragu Pasta", 620) == "any"
    assert infer_meal_type("Roasted Cauliflower Bowl", 480) == "any"


async def test_backfill_only_touches_null_rows(db_session):
    u = User(id=uuid.uuid4(), email=f"{uuid.uuid4()}@e.com", username=uuid.uuid4().hex[:8],
             hashed_password=hash_password("x"), email_verified=True, safe_mode=False,
             uses_custom_goals=False, is_admin=False)
    db_session.add(u)
    await db_session.flush()
    a = Recipe(id=uuid.uuid4(), user_id=u.id, name="Overnight Oats", servings=1.0, total_calories=300)
    b = Recipe(id=uuid.uuid4(), user_id=u.id, name="Pasta Bake", servings=1.0, total_calories=700)
    c = Recipe(id=uuid.uuid4(), user_id=u.id, name="Already Set", servings=1.0,
               total_calories=700, meal_type="dinner")
    db_session.add_all([a, b, c])
    await db_session.commit()

    n = await backfill_meal_types(db_session)
    await db_session.commit()
    assert n == 2

    rows = {r.name: r.meal_type for r in (await db_session.execute(
        Recipe.__table__.select())).fetchall()}
    assert rows["Overnight Oats"] == "breakfast"
    assert rows["Pasta Bake"] == "any"
    assert rows["Already Set"] == "dinner"

    assert await backfill_meal_types(db_session) == 0   # idempotent
