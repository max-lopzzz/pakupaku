from pathlib import Path

from recipe_import import extract_structured_recipe

FIXTURES = Path(__file__).parent / "fixtures"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text()


def test_extracts_top_level_recipe_jsonld():
    raw = extract_structured_recipe(_read("recipe_blog_jsonld.html"))
    assert raw is not None
    assert raw.name == "Simple Pancakes"
    assert raw.servings == 4.0
    assert raw.image_url == "https://example.com/pancakes.jpg"
    assert raw.ingredient_lines == [
        "2 cups all-purpose flour",
        "1/2 tsp salt",
        "3 large eggs",
        "1 clove garlic, minced",
    ]


def test_extracts_recipe_wrapped_in_graph():
    raw = extract_structured_recipe(_read("recipe_blog_graph.html"))
    assert raw is not None
    assert raw.name == "Graph Wrapped Soup"
    assert raw.servings == 6.0
    assert raw.image_url == "https://example.com/soup.jpg"
    assert raw.ingredient_lines == ["1 cup diced carrots", "2 tbsp olive oil"]


def test_returns_none_when_no_recipe_markup():
    assert extract_structured_recipe(_read("recipe_blog_none.html")) is None


def test_extract_structured_recipe_captures_instructions():
    html = """
    <script type="application/ld+json">
    {
      "@type": "Recipe",
      "name": "Soup",
      "recipeIngredient": ["1 cup broth"],
      "recipeInstructions": [
        {"@type": "HowToStep", "text": "Heat the broth."},
        {"@type": "HowToStep", "text": "Season and serve."}
      ]
    }
    </script>
    """
    result = extract_structured_recipe(html)
    assert result is not None
    assert result.instructions == "Heat the broth.\nSeason and serve."


def test_extract_structured_recipe_instructions_as_plain_strings():
    html = """
    <script type="application/ld+json">
    {
      "@type": "Recipe",
      "name": "Soup",
      "recipeIngredient": ["1 cup broth"],
      "recipeInstructions": ["Heat the broth.", "Season and serve."]
    }
    </script>
    """
    result = extract_structured_recipe(html)
    assert result.instructions == "Heat the broth.\nSeason and serve."


def test_extract_structured_recipe_no_instructions_is_none():
    html = """
    <script type="application/ld+json">
    {
      "@type": "Recipe",
      "name": "Soup",
      "recipeIngredient": ["1 cup broth"]
    }
    </script>
    """
    result = extract_structured_recipe(html)
    assert result.instructions is None
