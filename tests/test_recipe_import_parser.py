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
        ("½ cup sugar", 0.5, "cup", "sugar"),
        ("1½ cups flour", 1.5, "cup", "flour"),
        ("1 lb ground beef", 1.0, "lb", "ground beef"),
        ("1 kg potatoes", 1.0, "kg", "potatoes"),
        ("1 liter whole milk", 1.0, "l", "whole milk"),
        ("1 (14.5 oz) can diced tomatoes", 1.0, "can", "diced tomatoes"),
    ],
)
def test_parses_common_ingredient_lines(line, quantity, unit, food_name):
    parsed = parse_ingredient_line(line)
    assert parsed is not None
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


def test_returns_none_on_malformed_fraction_instead_of_raising():
    # "1/0" would raise ZeroDivisionError inside _parse_quantity; the
    # parser should treat this as unparseable and fall back to the LLM,
    # not propagate the exception.
    assert parse_ingredient_line("1/0 cup sugar") is None
