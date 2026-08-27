import asyncio

import httpx
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


# ─── SSRF guard ─────────────────────────────────────────────


class _NetworkCallNotExpectedClient:
    """A fake AsyncClient whose .get() fails the test loudly if called at
    all. Used to prove host validation rejects before any request goes
    out — without this, a real network attempt to a private address might
    fail with a connection error and produce the same 422 by accident,
    which would pass even if the validation logic were entirely missing."""

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, headers=None):
        raise AssertionError(
            f"fetch_page should have rejected {url!r} before making a request"
        )


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/recipe",
        "http://10.0.0.5/recipe",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/recipe",
    ],
)
def test_fetch_page_rejects_private_or_internal_hosts(url, monkeypatch):
    monkeypatch.setattr(
        recipe_import.httpx, "AsyncClient", _NetworkCallNotExpectedClient
    )
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(fetch_page(url))
    assert exc_info.value.status_code == 422
    detail = exc_info.value.detail.lower()
    assert "private" in detail or "internal" in detail


class _FakeFetchResponse:
    def __init__(self, status_code=200, headers=None, text=""):
        self.status_code = status_code
        self.headers = headers or {}
        self.text = text

    @property
    def is_redirect(self):
        return 300 <= self.status_code < 400

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "error", request=None, response=self  # type: ignore[arg-type]
            )


class _FakeFetchClient:
    """Stands in for httpx.AsyncClient as used by fetch_page. Set
    _FakeFetchClient.responses to a list of _FakeFetchResponse consumed in
    order, one per .get() call, before use."""

    responses = []
    calls = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, headers=None):
        _FakeFetchClient.calls.append(url)
        return _FakeFetchClient.responses.pop(0)


def test_fetch_page_returns_html_on_success(monkeypatch):
    _FakeFetchClient.responses = [
        _FakeFetchResponse(
            status_code=200,
            headers={"content-type": "text/html; charset=utf-8"},
            text="<html>hello</html>",
        )
    ]
    _FakeFetchClient.calls = []
    monkeypatch.setattr(recipe_import.httpx, "AsyncClient", _FakeFetchClient)

    result = asyncio.run(fetch_page("http://1.1.1.1/recipe"))

    assert result == "<html>hello</html>"


def test_fetch_page_follows_redirect_to_public_host(monkeypatch):
    _FakeFetchClient.responses = [
        _FakeFetchResponse(status_code=302, headers={"location": "http://8.8.8.8/final"}),
        _FakeFetchResponse(
            status_code=200,
            headers={"content-type": "text/html"},
            text="<html>final page</html>",
        ),
    ]
    _FakeFetchClient.calls = []
    monkeypatch.setattr(recipe_import.httpx, "AsyncClient", _FakeFetchClient)

    result = asyncio.run(fetch_page("http://1.1.1.1/start"))

    assert result == "<html>final page</html>"
    assert _FakeFetchClient.calls == ["http://1.1.1.1/start", "http://8.8.8.8/final"]


def test_fetch_page_rejects_redirect_to_private_ip(monkeypatch):
    _FakeFetchClient.responses = [
        _FakeFetchResponse(
            status_code=302, headers={"location": "http://127.0.0.1/secret"}
        )
    ]
    _FakeFetchClient.calls = []
    monkeypatch.setattr(recipe_import.httpx, "AsyncClient", _FakeFetchClient)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(fetch_page("http://1.1.1.1/recipe"))

    assert exc_info.value.status_code == 422
    detail = exc_info.value.detail.lower()
    assert "private" in detail or "internal" in detail
    # Only the first hop should have been requested — the redirect target
    # must be rejected by host validation before a second request is made.
    assert _FakeFetchClient.calls == ["http://1.1.1.1/recipe"]


def test_fetch_page_too_many_redirects(monkeypatch):
    _FakeFetchClient.responses = [
        _FakeFetchResponse(status_code=302, headers={"location": "http://1.1.1.1/next"})
        for _ in range(10)
    ]
    _FakeFetchClient.calls = []
    monkeypatch.setattr(recipe_import.httpx, "AsyncClient", _FakeFetchClient)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(fetch_page("http://1.1.1.1/start"))

    assert exc_info.value.status_code == 422
    assert "redirect" in exc_info.value.detail.lower()
    # Proves the loop actually iterated multiple times rather than
    # accepting/rejecting after a single call.
    assert len(_FakeFetchClient.calls) > 1
