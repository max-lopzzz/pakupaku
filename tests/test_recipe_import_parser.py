import pytest

from recipe_import import parse_ingredient_line


@pytest.mark.parametrize(
    "line,quantity,unit,food_name",
    [
        ("2 cups all-purpose flour", 2.0, "cup", "all-purpose flour"),
        ("1/2 tsp salt", 0.5, "tsp", "salt"),
        ("1 1/2 cups sugar", 1.5, "cup", "sugar"),
        ("3 large eggs", 3.0, "large", "eggs"),
        ("1 clove garlic, minced", 1.0, "clove", "garlic"),
        ("2 tbsp olive oil", 2.0, "tbsp", "olive oil"),
    ],
)
def test_parses_common_ingredient_lines(line, quantity, unit, food_name):
    parsed = parse_ingredient_line(line)
    assert parsed is not None
    assert parsed.raw_line == line
    assert parsed.quantity == quantity
    assert parsed.unit == unit
    assert parsed.food_name == food_name


def test_returns_none_with_no_leading_quantity():
    assert parse_ingredient_line("Salt to taste") is None


def test_defaults_to_grams_when_no_unit_word_follows():
    parsed = parse_ingredient_line("2 eggs")
    assert parsed is not None
    assert parsed.quantity == 2.0
    assert parsed.unit == "g"
    assert parsed.food_name == "eggs"
