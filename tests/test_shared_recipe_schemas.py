import pytest
from pydantic import ValidationError

from schemas import RecipeCreateRequest


def test_diet_tags_accepts_valid_values():
    req = RecipeCreateRequest(
        name="Test",
        servings=1,
        ingredients=[{"food_name": "rice", "amount_g": 100}],
        diet_tags=["vegan", "gluten_free"],
    )
    assert req.diet_tags == ["vegan", "gluten_free"]


def test_diet_tags_rejects_unknown_values():
    with pytest.raises(ValidationError):
        RecipeCreateRequest(
            name="Test",
            servings=1,
            ingredients=[{"food_name": "rice", "amount_g": 100}],
            diet_tags=["not_a_real_tag"],
        )
