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
    assert {o.id for o in buckets["breakfast"]} == {"b1"}   # strict: "any" is not a breakfast
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
    opts = [_opt("huge_b", "Huge B", "breakfast", 4000),   # way over every budget
            _opt("huge_l", "Huge L", "lunch", 4000)]
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


def test_aggregate_groceries_merges_by_normalized_name_and_sums():
    from meal_planner import aggregate_groceries
    items = [
        ("Oats", 150.0), ("oats", 50.0), ("  Oats  ", 25.0),   # merges: 225.0
        ("Banana", 118.0),
    ]
    result = aggregate_groceries(items)
    assert result == [
        {"key": "banana", "name": "Banana", "amount_g": 118.0},
        {"key": "oats", "name": "Oats", "amount_g": 225.0},
    ]


def test_aggregate_groceries_skips_blank_names_and_sorts_alphabetically():
    from meal_planner import aggregate_groceries
    items = [("Zucchini", 200.0), ("", 50.0), ("  ", 10.0), ("Apple", 150.0)]
    result = aggregate_groceries(items)
    assert [it["key"] for it in result] == ["apple", "zucchini"]


def test_aggregate_groceries_rounds_amounts():
    from meal_planner import aggregate_groceries
    result = aggregate_groceries([("Rice", 100.333), ("Rice", 50.111)])
    assert result == [{"key": "rice", "name": "Rice", "amount_g": 150.4}]


def test_aggregate_groceries_empty_input():
    from meal_planner import aggregate_groceries
    assert aggregate_groceries([]) == []


# ── slot fit & variety ───────────────────────────────────────────────────────

def test_breakfast_bucket_only_takes_recipes_tagged_breakfast():
    # Most imported recipes are "any" (no breakfast word in the name). "any"
    # is fine for lunch/dinner but must never fill a breakfast slot — that is
    # how Sushi Wraps and lentil soup ended up as breakfast.
    opts = [
        _opt("b1", "Overnight Oats", "breakfast", 350),
        _opt("m1", "Veggie Noodle Stir Fry", "any", 600),
        _opt("m2", "Lentil Soup", "any", 500),
    ]
    buckets = build_buckets(opts, frozenset(), ["breakfast", "lunch", "dinner"])
    assert [o.id for o in buckets["breakfast"]] == ["b1"]
    assert {o.id for o in buckets["lunch"]} == {"m1", "m2"}     # "any" still fits lunch/dinner
    assert {o.id for o in buckets["dinner"]} == {"m1", "m2"}


def test_a_library_with_no_breakfast_recipes_leaves_breakfast_unfilled():
    opts = [_opt("m1", "Stir Fry", "any", 600), _opt("m2", "Soup", "any", 500)]
    plan = generate_plan(opts, days=2, meals_per_day=3,
                         targets={"kcal": 2000.0, "protein_g": None, "fat_g": None, "carbs_g": None},
                         diet_tags=frozenset(), seed=1)
    for day in plan:
        breakfast = [e for e in day.entries if e.slot == "breakfast"][0]
        assert breakfast.unfilled        # honest gap, not a stir fry for breakfast


def _realistic(id, name, mt, kcal):
    # macros proportional to calories, like a real recipe — a pool where every
    # recipe has the same macros per serving quietly favours low-calorie ones
    # (scaled to more servings) and can mask a slot-fit bug.
    return _opt(id, name, mt, kcal, p=kcal * 0.05, f=kcal * 0.035, c=kcal * 0.10, fib=kcal * 0.01)


def _big_pool():
    pool = []
    for i in range(10):
        pool.append(_realistic("b%d" % i, "Breakfast %d" % i, "breakfast", 350 + i * 10))
    for i in range(40):
        pool.append(_realistic("m%d" % i, "Main %d" % i, "any", 550 + i * 5))
    return pool


TARGETS = {"kcal": 2000.0, "protein_g": 120.0, "fat_g": 65.0, "carbs_g": 220.0}


def test_generated_breakfasts_are_always_breakfast_recipes():
    for seed in range(15):
        plan = generate_plan(_big_pool(), days=7, meals_per_day=3, targets=TARGETS,
                             diet_tags=frozenset(), seed=seed)
        for day in plan:
            for e in day.entries:
                if e.slot == "breakfast":
                    assert e.option.id.startswith("b"), e.option.name


def test_no_recipe_repeats_within_a_plan_when_the_pool_has_enough():
    # 10 breakfasts for 7 days, 40 mains for 14 lunch/dinner slots: nothing
    # forces a repeat, so there must not be one — not on adjacent days, and
    # not on days further apart either.
    for seed in range(40):
        plan = generate_plan(_big_pool(), days=7, meals_per_day=3, targets=TARGETS,
                             diet_tags=frozenset(), seed=seed)
        ids = [e.option.id for d in plan for e in d.entries if e.option]
        assert len(ids) == 21
        assert len(set(ids)) == len(ids), "seed %d repeated a recipe" % seed


def test_repeats_only_start_once_a_slot_has_run_out_of_fresh_recipes():
    # Only 2 breakfast recipes for 5 days: both are used before either repeats,
    # and the plan still fills every breakfast rather than leaving gaps.
    opts = [_opt("b0", "B0", "breakfast", 400), _opt("b1", "B1", "breakfast", 420)]
    opts += [_opt("m%d" % i, "Main %d" % i, "any", 600) for i in range(30)]
    plan = generate_plan(opts, days=5, meals_per_day=3, targets=TARGETS,
                         diet_tags=frozenset(), seed=3)
    breakfasts = [[e for e in d.entries if e.slot == "breakfast"][0] for d in plan]
    assert all(not b.unfilled for b in breakfasts)
    assert {b.option.id for b in breakfasts[:2]} == {"b0", "b1"}
    # the mains still never repeat
    mains = [e.option.id for d in plan for e in d.entries if e.slot != "breakfast"]
    assert len(set(mains)) == len(mains)


def test_swap_entry_avoids_recipes_already_elsewhere_in_the_plan():
    from meal_planner import _scaled_entry
    opts = [_opt("l_cur", "Cur", "lunch", 650), _opt("l_used", "Used", "lunch", 650),
            _opt("l_fresh", "Fresh", "lunch", 650)]
    budgets = slot_budgets(1900.0, ["breakfast", "lunch"])
    day_target = {"kcal": 1900.0, "protein_g": None, "fat_g": None, "carbs_g": None}
    day_entries = [_scaled_entry("breakfast", None, budgets["breakfast"]),
                   _scaled_entry("lunch", opts[0], budgets["lunch"])]
    for seed in range(10):
        repl = swap_entry(opts, day_entries, "lunch", budgets, day_target, frozenset(),
                          exclude_recipe_id="l_cur", seed=seed,
                          avoid_recipe_ids=frozenset({"l_used"}))
        assert repl.option.id == "l_fresh"


def test_swap_entry_falls_back_to_a_repeat_when_nothing_fresh_is_left():
    from meal_planner import _scaled_entry
    opts = [_opt("l_cur", "Cur", "lunch", 650), _opt("l_used", "Used", "lunch", 650)]
    budgets = slot_budgets(1900.0, ["breakfast", "lunch"])
    day_target = {"kcal": 1900.0, "protein_g": None, "fat_g": None, "carbs_g": None}
    day_entries = [_scaled_entry("breakfast", None, budgets["breakfast"]),
                   _scaled_entry("lunch", opts[0], budgets["lunch"])]
    repl = swap_entry(opts, day_entries, "lunch", budgets, day_target, frozenset(),
                      exclude_recipe_id="l_cur", seed=1, avoid_recipe_ids=frozenset({"l_used"}))
    assert repl is not None and repl.option.id == "l_used"      # better a repeat than a dead button


def test_infer_meal_type_recognises_more_breakfast_dishes():
    for name in ["Spinach Feta Omelette", "Sweet Potato Hash Breakfast Bowl", "Easy Frittata",
                 "Shakshuka", "Banana Oatmeal", "Chia Parfait", "Everything Bagel", "Dutch Baby Crepes",
                 "Homemade Muesli"]:
        assert infer_meal_type(name, 450) == "breakfast", name


def test_infer_meal_type_recognises_baked_sweets_as_snacks():
    for name in ["Vegan Scones", "Blueberry Muffins", "Korean Rice Krispies with Dried Jeju Mandarins",
                 "Crispy Rice Treats", "Glazed Donuts", "Almond Biscotti", "Cheesecake Bars"]:
        assert infer_meal_type(name, 380) == "snack", name
    # ...without catching ordinary mains
    for name in ["Chicken Parmesan", "Veggie Noodle Stir Fry with Peanut Lime Sauce",
                 "Creamy Red Lentil and Sweet Potato Soup", "Greek-Style Potato Nachos",
                 "Roasted Sweet Potato Tabbouleh Bowl", "Sushi Wraps",
                 "Popcorn Chicken", "Truffle Mushroom Pasta", "Pretzel-Crusted Chicken"]:
        assert infer_meal_type(name, 520) == "any", name
