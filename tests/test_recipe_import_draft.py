import asyncio

import pytest
from fastapi import HTTPException

import recipe_import
from recipe_import import (
    ParsedIngredient,
    RawRecipe,
    build_import_draft,
)
from schemas import ImportedIngredient


def _stub_common(monkeypatch, *, structured=None, llm=None):
    async def fake_fetch_page(url):
        return "<html>fake page</html>"

    async def fake_extract_via_llm(html):
        return llm

    def fake_parse_line(line):
        return ParsedIngredient(raw_line=line, quantity=1.0, unit="g", food_name=line)

    async def fake_match_ingredient(parsed):
        return ImportedIngredient(
            raw_line=parsed.raw_line,
            quantity=parsed.quantity,
            unit=parsed.unit,
            food_name=parsed.food_name,
            best_match=None,
            alternates=[],
        )

    monkeypatch.setattr(recipe_import, "fetch_page", fake_fetch_page)
    monkeypatch.setattr(
        recipe_import, "extract_structured_recipe", lambda html: structured
    )
    monkeypatch.setattr(recipe_import, "extract_recipe_via_llm", fake_extract_via_llm)
    monkeypatch.setattr(recipe_import, "parse_ingredient_line", fake_parse_line)
    monkeypatch.setattr(recipe_import, "match_ingredient", fake_match_ingredient)


def test_uses_structured_extraction_when_available(monkeypatch):
    structured = RawRecipe(
        name="Structured Recipe",
        servings=2.0,
        image_url="https://example.com/img.jpg",
        ingredient_lines=["1 cup rice"],
    )
    _stub_common(monkeypatch, structured=structured)

    draft = asyncio.run(build_import_draft("https://example.com/recipe"))

    assert draft.name == "Structured Recipe"
    assert draft.servings == 2.0
    assert draft.image_url == "https://example.com/img.jpg"
    assert draft.source_url == "https://example.com/recipe"
    assert len(draft.ingredients) == 1


def test_falls_back_to_llm_when_no_structured_data(monkeypatch):
    llm_result = RawRecipe(
        name="LLM Recipe", servings=1.0, image_url=None, ingredient_lines=["1 egg"]
    )
    _stub_common(monkeypatch, structured=None, llm=llm_result)

    draft = asyncio.run(build_import_draft("https://example.com/recipe"))

    assert draft.name == "LLM Recipe"
    assert len(draft.ingredients) == 1


def test_raises_422_when_neither_extraction_finds_a_recipe(monkeypatch):
    _stub_common(monkeypatch, structured=None, llm=None)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(build_import_draft("https://example.com/recipe"))
    assert exc_info.value.status_code == 422
