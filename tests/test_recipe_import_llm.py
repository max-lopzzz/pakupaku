import json

import httpx
import pytest
from fastapi import HTTPException

import recipe_import


class _FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "error", request=None, response=self  # type: ignore[arg-type]
            )

    def json(self):
        return self._payload


class _FakeAsyncClient:
    """Stands in for httpx.AsyncClient as an async context manager."""

    last_request = None  # captured for assertions

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, headers=None, json=None):
        _FakeAsyncClient.last_request = {"url": url, "headers": headers, "json": json}
        content = _FakeAsyncClient.next_content
        return _FakeResponse(
            {"choices": [{"message": {"content": content}}]}
        )


def _install_fake_client(monkeypatch, content: str):
    _FakeAsyncClient.next_content = content
    monkeypatch.setattr(recipe_import.httpx, "AsyncClient", _FakeAsyncClient)


def test_extract_recipe_via_llm_parses_response(monkeypatch):
    monkeypatch.setattr(recipe_import, "LLM_API_KEY", "test-key")
    _install_fake_client(
        monkeypatch,
        json.dumps(
            {
                "name": "LLM Extracted Soup",
                "servings": 2,
                "ingredient_lines": ["1 cup broth", "2 carrots"],
            }
        ),
    )

    import asyncio

    raw = asyncio.run(recipe_import.extract_recipe_via_llm("<html>...</html>"))

    assert raw is not None
    assert raw.name == "LLM Extracted Soup"
    assert raw.servings == 2.0
    assert raw.ingredient_lines == ["1 cup broth", "2 carrots"]
    assert _FakeAsyncClient.last_request["json"]["model"] == recipe_import.LLM_MODEL


def test_extract_recipe_via_llm_returns_none_when_no_recipe_found(monkeypatch):
    monkeypatch.setattr(recipe_import, "LLM_API_KEY", "test-key")
    _install_fake_client(
        monkeypatch,
        json.dumps({"name": None, "servings": None, "ingredient_lines": []}),
    )

    import asyncio

    assert asyncio.run(recipe_import.extract_recipe_via_llm("<html></html>")) is None


def test_extract_recipe_via_llm_raises_503_when_not_configured(monkeypatch):
    monkeypatch.setattr(recipe_import, "LLM_API_KEY", None)

    import asyncio

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(recipe_import.extract_recipe_via_llm("<html></html>"))
    assert exc_info.value.status_code == 503


def test_extract_recipe_via_llm_raises_502_on_request_failure(monkeypatch):
    monkeypatch.setattr(recipe_import, "LLM_API_KEY", "test-key")

    class _FailingClient(_FakeAsyncClient):
        async def post(self, url, headers=None, json=None):
            raise httpx.TimeoutException("timed out")

    monkeypatch.setattr(recipe_import.httpx, "AsyncClient", _FailingClient)

    import asyncio

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(recipe_import.extract_recipe_via_llm("<html></html>"))
    assert exc_info.value.status_code == 502


def test_extract_recipe_via_llm_raises_502_on_empty_choices_array(monkeypatch):
    monkeypatch.setattr(recipe_import, "LLM_API_KEY", "test-key")

    class _EmptyChoicesClient(_FakeAsyncClient):
        async def post(self, url, headers=None, json=None):
            _FakeAsyncClient.last_request = {"url": url, "headers": headers, "json": json}
            return _FakeResponse({"choices": []})

    monkeypatch.setattr(recipe_import.httpx, "AsyncClient", _EmptyChoicesClient)

    import asyncio

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(recipe_import.extract_recipe_via_llm("<html></html>"))
    assert exc_info.value.status_code == 502


def test_parse_ingredient_line_via_llm_parses_response(monkeypatch):
    monkeypatch.setattr(recipe_import, "LLM_API_KEY", "test-key")
    _install_fake_client(
        monkeypatch,
        json.dumps({"quantity": 1, "unit": "pinch", "food_name": "saffron"}),
    )

    import asyncio

    parsed = asyncio.run(
        recipe_import.parse_ingredient_line_via_llm("a pinch of saffron")
    )

    assert parsed.raw_line == "a pinch of saffron"
    assert parsed.quantity == 1.0
    assert parsed.unit == "pinch"
    assert parsed.food_name == "saffron"
