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


import random as _random

from meal_planner import (
    RecipeOption, PlannedDay, active_slots, slot_budgets, build_buckets, plan_day,
)


def _opt(id, name, mt, kcal, p=20.0, f=20.0, c=40.0, fib=5.0, tags=()):
    return RecipeOption(id=id, name=name, meal_type=mt, diet_tags=frozenset(tags),
                        kcal=kcal, protein_g=p, fat_g=f, carbs_g=c, fiber_g=fib)


def test_active_slots():
    assert active_slots(2) == ["breakfast", "lunch"]
    assert active_slots(3) == ["breakfast", "lunch", "dinner"]
    assert active_slots(4) == ["breakfast", "lunch", "dinner", "snack"]


def test_slot_budgets_renormalise_and_sum_to_target():
    b = slot_budgets(2000.0, ["breakfast", "lunch", "dinner"])
    assert round(sum(b.values())) == 2000
    # 0.25 / 0.35 / 0.35 -> renormalised over 0.95
    assert b["breakfast"] < b["lunch"]
    assert abs(b["lunch"] - b["dinner"]) < 1e-6


def test_build_buckets_meal_type_and_diet_filter():
    opts = [
        _opt("b1", "Oats", "breakfast", 300),
        _opt("s1", "Bliss Balls", "snack", 120),
        _opt("a1", "Any Bowl", "any", 500),
        _opt("a2", "Tiny Any", "any", 150),
        _opt("d1", "Steak", "dinner", 700),  # no tags
        _opt("v1", "Vegan Bowl", "any", 480, tags=("vegan",)),
    ]
    buckets = build_buckets(opts, frozenset(), ["breakfast", "lunch", "dinner", "snack"])
    assert {o.id for o in buckets["breakfast"]} == {"b1", "a1", "a2", "v1"}
    assert {o.id for o in buckets["dinner"]} == {"d1", "a1", "a2", "v1"}
    assert {o.id for o in buckets["snack"]} == {"s1", "a2"}   # snack + low-cal any
    assert "s1" not in {o.id for o in buckets["dinner"]}

    vegan = build_buckets(opts, frozenset({"vegan"}), ["lunch"])
    assert {o.id for o in vegan["lunch"]} == {"v1"}


def test_plan_day_picks_the_closest_combination():
    rng = _random.Random(0)
    # exactly-right recipe per slot at 1x servings for a 2000 kcal day, 3 meals
    budgets = slot_budgets(2000.0, ["breakfast", "lunch", "dinner"])
    opts = [
        _opt("good_b", "Good B", "breakfast", budgets["breakfast"], p=30, f=15, c=60),
        _opt("good_l", "Good L", "lunch", budgets["lunch"], p=45, f=25, c=80),
        _opt("good_d", "Good D", "dinner", budgets["dinner"], p=45, f=25, c=80),
        _opt("bad", "Way Off", "any", 50, p=1, f=1, c=1),
    ]
    buckets = build_buckets(opts, frozenset(), ["breakfast", "lunch", "dinner"])
    day = plan_day(
        buckets,
        {"kcal": 2000.0, "protein_g": 120.0, "fat_g": 65.0, "carbs_g": 220.0},
        budgets, frozenset(), rng, n=400,
    )
    chosen = {e.option.id for e in day.entries}
    assert chosen == {"good_b", "good_l", "good_d"}
    assert abs(day.totals["kcal"] - 2000.0) < 60


def test_plan_day_servings_clamped_when_pool_is_far_from_budget():
    rng = _random.Random(1)
    budgets = slot_budgets(2000.0, ["breakfast", "lunch"])
    opts = [_opt("huge", "Huge", "any", 4000)]   # 1 recipe, way over every budget
    buckets = build_buckets(opts, frozenset(), ["breakfast", "lunch"])
    day = plan_day(buckets, {"kcal": 2000.0, "protein_g": None, "fat_g": None, "carbs_g": None},
                   budgets, frozenset(), rng, n=50)
    assert all(e.servings == 0.5 for e in day.entries)


def test_plan_day_unfilled_slot_when_bucket_empty():
    rng = _random.Random(2)
    budgets = slot_budgets(2000.0, ["breakfast", "lunch", "dinner", "snack"])
    opts = [_opt("b", "B", "breakfast", 500), _opt("a", "A", "any", 600)]  # nothing for snack
    buckets = build_buckets(opts, frozenset(), ["breakfast", "lunch", "dinner", "snack"])
    day = plan_day(buckets, {"kcal": 2000.0, "protein_g": None, "fat_g": None, "carbs_g": None},
                   budgets, frozenset(), rng, n=50)
    snack = [e for e in day.entries if e.slot == "snack"][0]
    assert snack.unfilled
    assert snack.kcal == 0.0
