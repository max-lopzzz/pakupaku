"""
A ``DateTime`` column (no ``timezone=True``) round-trips as a naive
Python ``datetime`` on both SQLite and Postgres, even though every value
is written with ``datetime.utcnow()``. Serialized as-is, that naive value
carries no "Z"/offset — and ``new Date("2026-09-15T00:00:00")`` in
JavaScript treats those digits as *local* time rather than converting
from UTC, so a food log made at 18:00 (in a timezone behind UTC) rendered
as "00:00". ``schemas._utc()`` fixes this at the API boundary; these
tests cover the helper and its per-field application on the response
schemas that display a clock time to the user.
"""

from datetime import datetime, timezone

from schemas import _utc, FoodLogResponse, MealPlanDayResponse


def test_utc_tags_a_naive_datetime_without_shifting_the_wall_clock():
    naive = datetime(2026, 9, 15, 0, 1, 0)
    tagged = _utc(naive)
    assert tagged.tzinfo is timezone.utc
    assert (tagged.year, tagged.month, tagged.day, tagged.hour, tagged.minute) == (2026, 9, 15, 0, 1)


def test_utc_leaves_an_already_aware_datetime_untouched():
    aware = datetime(2026, 9, 15, 0, 1, 0, tzinfo=timezone.utc)
    assert _utc(aware) is aware


def _food_log_kwargs(**overrides):
    kwargs = dict(
        id="11111111-1111-1111-1111-111111111111",
        user_id="11111111-1111-1111-1111-111111111111",
        log_date="2026-09-15",
        logged_at=datetime(2026, 9, 15, 0, 1, 0),   # naive, as read back from the DB
        food_id=None, recipe_id=None, food_name="Tacos", brand_name=None,
        amount_g=100.0, calories=None, protein_g=None, fat_g=None, carbs_g=None,
        fiber_g=None, sugar_g=None, sodium_mg=None, meal=None,
    )
    kwargs.update(overrides)
    return kwargs


def test_food_log_response_stamps_logged_at_as_utc():
    resp = FoodLogResponse(**_food_log_kwargs())
    assert resp.logged_at.tzinfo is timezone.utc


def test_food_log_response_json_carries_an_explicit_utc_marker():
    resp = FoodLogResponse(**_food_log_kwargs())
    # "Z" (or an explicit offset) is what lets `new Date(...)` on the
    # frontend correctly convert to the viewer's local time instead of
    # misreading the naive digits as already-local.
    body = resp.model_dump_json()
    assert '"logged_at":"2026-09-15T00:01:00Z"' in body


def test_meal_plan_day_response_logged_at_none_passes_through():
    day = MealPlanDayResponse(
        day_index=0, logged_at=None, entries=[], totals={}, structurally_unfilled_slots=[],
    )
    assert day.logged_at is None


def test_meal_plan_day_response_logged_at_gets_stamped_when_present():
    day = MealPlanDayResponse(
        day_index=0, logged_at=datetime(2026, 9, 15, 0, 1, 0),
        entries=[], totals={}, structurally_unfilled_slots=[],
    )
    assert day.logged_at.tzinfo is timezone.utc
