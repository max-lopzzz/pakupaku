"""
test_food_model.py
------------------
The `foods` table created from `models.Food` must match the offline build
pipeline's schema exactly — same columns, same order — so that a database
built by `scripts/build_food_db` is query-compatible with the ORM.
"""

from sqlalchemy import text


async def test_foods_table_has_the_pipeline_schema(db_session):
    rows = (await db_session.execute(text("PRAGMA table_info(foods)"))).fetchall()
    names = [r[1] for r in rows]
    assert names == [
        "id", "canonical_name", "aliases", "category", "prep_state",
        "calories_per_100g", "protein_per_100g", "fat_per_100g", "carbs_per_100g",
        "fiber_per_100g", "sugar_per_100g", "sodium_mg_per_100g", "calcium_mg_per_100g",
        "iron_mg_per_100g", "vitamin_c_mg_per_100g", "vitamin_d_mcg_per_100g",
        "vitamin_b12_mcg_per_100g", "portions", "source_ids", "source_count",
    ]
