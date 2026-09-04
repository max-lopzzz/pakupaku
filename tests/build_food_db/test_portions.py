from scripts.build_food_db.aggregate import AggregatedFood
from scripts.build_food_db.portions import attach_portions


def _food(name):
    return AggregatedFood(canonical_name=name, prep_state="raw", category=None,
                          source_ids=["usda", "cofid"], source_count=2,
                          calories_per_100g=1.0)


def test_exact_key_match_attaches_portions():
    portions = {"rice white": [{"unit": "cup", "grams": 186.0}]}
    out = attach_portions([_food("White rice")], portions)
    assert out[0][1] == [{"unit": "cup", "grams": 186.0}]


def test_no_match_yields_empty_portions():
    out = attach_portions([_food("Obscure gourd")], {"rice white": [{"unit": "cup", "grams": 186.0}]})
    assert out[0][1] == []
