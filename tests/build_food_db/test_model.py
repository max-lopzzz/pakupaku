from scripts.build_food_db.model import NUTRIENT_FIELDS, NormalisedRow


def test_nutrient_fields_are_the_twelve_extract_nutrients_columns():
    assert NUTRIENT_FIELDS == (
        "calories_per_100g", "protein_per_100g", "fat_per_100g",
        "carbs_per_100g", "fiber_per_100g", "sugar_per_100g",
        "sodium_mg_per_100g", "calcium_mg_per_100g", "iron_mg_per_100g",
        "vitamin_c_mg_per_100g", "vitamin_d_mcg_per_100g", "vitamin_b12_mcg_per_100g",
    )


def test_normalised_row_nutrients_returns_all_twelve_keys():
    row = NormalisedRow(
        source_id="usda", source_food_id="123", name="Broccoli, raw",
        canonical_key="", prep_state="", category="vegetable",
        calories_per_100g=34.0, protein_per_100g=2.8,
    )
    n = row.nutrients()
    assert set(n) == set(NUTRIENT_FIELDS)
    assert n["calories_per_100g"] == 34.0
    assert n["fiber_per_100g"] is None
