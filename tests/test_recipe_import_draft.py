import asyncio

import pytest
from fastapi import HTTPException

import recipe_import
from recipe_import import (
    ParsedIngredient,
    RawRecipe,
    build_import_draft,
    fetch_page,
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


def test_contains_ingredient_match_failures(monkeypatch):
    """Verify that if match_ingredient raises an exception for some
    ingredients, the gather doesn't fail the whole import — instead,
    those ingredients get best_match=None."""
    structured = RawRecipe(
        name="Test Recipe",
        servings=1.0,
        image_url=None,
        ingredient_lines=["1 cup flour", "2 eggs", "1 tsp salt"],
    )

    async def fake_fetch_page(url):
        return "<html>fake page</html>"

    def fake_parse_line(line):
        return ParsedIngredient(raw_line=line, quantity=1.0, unit="g", food_name=line)

    async def failing_match_ingredient(parsed):
        raise RuntimeError("Network failure: dropped connection")

    monkeypatch.setattr(recipe_import, "fetch_page", fake_fetch_page)
    monkeypatch.setattr(
        recipe_import, "extract_structured_recipe", lambda html: structured
    )
    monkeypatch.setattr(recipe_import, "parse_ingredient_line", fake_parse_line)
    monkeypatch.setattr(recipe_import, "match_ingredient", failing_match_ingredient)

    # Should not raise — _safe_match_ingredient catches the exception
    draft = asyncio.run(build_import_draft("https://example.com/recipe"))

    assert draft.name == "Test Recipe"
    assert len(draft.ingredients) == 3
    # All ingredients should have best_match=None because match_ingredient failed
    for ingredient in draft.ingredients:
        assert ingredient.best_match is None
        assert ingredient.alternates == []


def test_llm_fallback_failure_degrades_gracefully_per_line(monkeypatch):
    """If a line has no parseable leading quantity and the LLM fallback is
    unavailable (503) or fails (502), build_import_draft should not fail
    the whole import — it should degrade that one line to a raw fallback
    ingredient instead of propagating the HTTPException."""
    structured = RawRecipe(
        name="Test Recipe",
        servings=1.0,
        image_url=None,
        ingredient_lines=["salt to taste", "a pinch of saffron"],
    )

    async def fake_fetch_page(url):
        return "<html>fake page</html>"

    def fake_parse_line(line):
        # Always fails to find a leading quantity, forcing the LLM fallback.
        return None

    async def failing_parse_via_llm(line):
        raise HTTPException(status_code=503, detail="not configured")

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
    monkeypatch.setattr(recipe_import, "parse_ingredient_line", fake_parse_line)
    monkeypatch.setattr(
        recipe_import, "parse_ingredient_line_via_llm", failing_parse_via_llm
    )
    monkeypatch.setattr(recipe_import, "match_ingredient", fake_match_ingredient)

    # Should not raise — the per-line HTTPException from the LLM fallback
    # is caught and degraded to a raw fallback ingredient.
    draft = asyncio.run(build_import_draft("https://example.com/recipe"))

    assert draft.name == "Test Recipe"
    assert len(draft.ingredients) == 2
    for ingredient, line in zip(draft.ingredients, structured.ingredient_lines):
        assert ingredient.raw_line == line
        assert ingredient.food_name == line


def test_fetch_page_raises_422_on_invalid_url():
    """httpx.InvalidURL (e.g. a malformed IPv6 host) subclasses Exception
    directly, not httpx.RequestError, so it needs its own except clause
    in fetch_page — otherwise it would propagate as an unhandled 500."""
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(fetch_page("http://[::1"))
    assert exc_info.value.status_code == 422
