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


def test_infer_meal_type_ambiguous_keywords_match_whole_words_only():
    # "oat" must not fire inside "Goat", "toast" not inside "Toasted",
    # "dip" not inside "Dippers".
    assert infer_meal_type("Goat Cheese Salad", 420) != "breakfast"
    assert infer_meal_type("Goat Cheese Salad", 420) == "any"
    assert infer_meal_type("Toasted Sesame Noodles", 610) != "breakfast"
    assert infer_meal_type("Toasted Sesame Noodles", 610) == "any"
    # "Chicken Dippers" is not a snack by keyword — it falls through to the
    # kcal rule (or "any" when kcal is high / unknown).
    assert infer_meal_type("Chicken Dippers", 520) == "any"
    assert infer_meal_type("Chicken Dippers", None) == "any"
    assert infer_meal_type("Chicken Dippers", 150) == "snack"  # low-kcal rule, not keyword
    # the real breakfast/snack words still work as whole words
    assert infer_meal_type("Overnight Oats", 300) == "breakfast"
    assert infer_meal_type("Sourdough Toast", 250) == "breakfast"
    assert infer_meal_type("Spinach Dip", 180) == "snack"
    assert infer_meal_type("Dark Chocolate Bark", 190) == "snack"
    assert infer_meal_type("Protein Bar", 210) == "snack"


def test_infer_meal_type_desserts_and_drinks_are_snacks_not_any():
    # These aren't full meals, so they must not fall through to "any" —
    # the planning engine treats "any" as eligible for breakfast/lunch/
    # dinner, which is how a plan ended up serving hot chocolate for
    # breakfast and an ice cream sandwich for dinner.
    assert infer_meal_type("Pink Hot Chocolate", 380) == "snack"
    assert infer_meal_type("Cotton Candy Ice Cream Sandwiches", 420) == "snack"
    assert infer_meal_type("Salted Caramel Milkshake", 550) == "snack"
    assert infer_meal_type("Double Chocolate Fudge Brownies", 340) == "snack"
    assert infer_meal_type("Classic Chocolate Chip Cookies", 210) == "snack"
    assert infer_meal_type("Vanilla Bean Cupcakes", 300) == "snack"
    assert infer_meal_type("Strawberry Lemonade", 120) == "snack"
    assert infer_meal_type("Rainbow Sherbet Popsicles", 150) == "snack"


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


async def test_reclassify_any_meal_types_only_touches_any_rows(db_session):
    from meal_planner import reclassify_any_meal_types

    u = User(id=uuid.uuid4(), email=f"{uuid.uuid4()}@e.com", username=uuid.uuid4().hex[:8],
             hashed_password=hash_password("x"), email_verified=True, safe_mode=False,
             uses_custom_goals=False, is_admin=False)
    db_session.add(u)
    await db_session.flush()
    # classified "any" by an older heuristic that didn't know "hot chocolate"
    stale = Recipe(id=uuid.uuid4(), user_id=u.id, name="Pink Hot Chocolate", servings=1.0,
                    total_calories=380, meal_type="any")
    # still correctly "any" under the improved heuristic
    still_any = Recipe(id=uuid.uuid4(), user_id=u.id, name="Lentil Ragu Pasta", servings=1.0,
                        total_calories=620, meal_type="any")
    # a human's deliberate choice — must not be touched even though the
    # name would otherwise reclassify
    deliberate = Recipe(id=uuid.uuid4(), user_id=u.id, name="Ice Cream Float", servings=1.0,
                         total_calories=300, meal_type="dinner")
    db_session.add_all([stale, still_any, deliberate])
    await db_session.commit()

    result = await reclassify_any_meal_types(db_session)
    await db_session.commit()
    assert result == {"scanned": 2, "reclassified": 1}

    rows = {r.name: r.meal_type for r in (await db_session.execute(
        Recipe.__table__.select())).fetchall()}
    assert rows["Pink Hot Chocolate"] == "snack"
    assert rows["Lentil Ragu Pasta"] == "any"
    assert rows["Ice Cream Float"] == "dinner"

    assert await reclassify_any_meal_types(db_session) == {"scanned": 1, "reclassified": 0}  # idempotent


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


from meal_planner import generate_plan, swap_entry


def test_generate_plan_shape_and_determinism():
    opts = [
        _opt("b", "Oats", "breakfast", 450, p=20, f=12, c=70),
        _opt("l", "Salad", "lunch", 650, p=35, f=25, c=70),
        _opt("d", "Curry", "dinner", 700, p=40, f=25, c=80),
        _opt("d2", "Stew", "dinner", 680, p=38, f=22, c=78),
    ]
    tgt = {"kcal": 1900.0, "protein_g": 110.0, "fat_g": 60.0, "carbs_g": 220.0}
    a = generate_plan(opts, days=2, meals_per_day=3, targets=tgt, diet_tags=frozenset(), seed=7)
    b = generate_plan(opts, days=2, meals_per_day=3, targets=tgt, diet_tags=frozenset(), seed=7)
    assert len(a) == 2
    assert all(len(day.entries) == 3 for day in a)
    assert [[e.option.id for e in d.entries] for d in a] == [[e.option.id for e in d.entries] for d in b]


def test_generate_plan_empty_bucket_leaves_slot_unfilled_not_crash():
    opts = [_opt("b", "Oats", "breakfast", 450)]   # nothing for lunch/dinner/snack
    tgt = {"kcal": 1800.0, "protein_g": None, "fat_g": None, "carbs_g": None}
    plan = generate_plan(opts, days=1, meals_per_day=3, targets=tgt, diet_tags=frozenset(), seed=1)
    slots = {e.slot: e for e in plan[0].entries}
    assert not slots["breakfast"].unfilled
    assert slots["lunch"].unfilled and slots["dinner"].unfilled


def test_swap_entry_excludes_current_and_returns_best_alternative():
    opts = [
        _opt("keep_b", "B", "breakfast", 450),
        _opt("cur_l", "Cur L", "lunch", 640),
        _opt("alt_l", "Alt L", "lunch", 650, p=40, f=20, c=75),
        _opt("keep_d", "D", "dinner", 700),
    ]
    budgets = slot_budgets(1900.0, ["breakfast", "lunch", "dinner"])
    day_target = {"kcal": 1900.0, "protein_g": 110.0, "fat_g": 60.0, "carbs_g": 220.0}
    # a day whose lunch is cur_l
    from meal_planner import _scaled_entry
    day_entries = [
        _scaled_entry("breakfast", opts[0], budgets["breakfast"]),
        _scaled_entry("lunch", opts[1], budgets["lunch"]),
        _scaled_entry("dinner", opts[3], budgets["dinner"]),
    ]
    repl = swap_entry(opts, day_entries, "lunch", budgets, day_target,
                      frozenset(), exclude_recipe_id="cur_l", seed=3)
    assert repl is not None
    assert repl.option.id == "alt_l"


def test_swap_entry_returns_none_when_no_alternative():
    opts = [_opt("only_l", "Only", "lunch", 640)]
    budgets = slot_budgets(1900.0, ["breakfast", "lunch"])
    from meal_planner import _scaled_entry
    day_entries = [
        _scaled_entry("breakfast", None, budgets["breakfast"]),
        _scaled_entry("lunch", opts[0], budgets["lunch"]),
    ]
    repl = swap_entry(opts, day_entries, "lunch", budgets,
                      {"kcal": 1900.0, "protein_g": None, "fat_g": None, "carbs_g": None},
                      frozenset(), exclude_recipe_id="only_l", seed=1)
    assert repl is None
