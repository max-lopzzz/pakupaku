# tests/test_main_recipes_import.py
from fastapi.testclient import TestClient

import main
from auth import get_current_user
from main import app
from schemas import RecipeImportDraft


class _FakeUser:
    id = "00000000-0000-0000-0000-000000000000"


def _override_current_user():
    return _FakeUser()


def test_import_recipe_returns_draft(monkeypatch):
    async def fake_build_import_draft(url):
        assert url == "https://example.com/recipe"
        return RecipeImportDraft(
            name="Test Recipe",
            servings=2.0,
            image_url=None,
            ingredients=[],
            source_url=url,
        )

    monkeypatch.setattr(main, "build_import_draft", fake_build_import_draft)
    app.dependency_overrides[get_current_user] = _override_current_user
    try:
        client = TestClient(app)
        res = client.post(
            "/recipes/import", json={"url": "https://example.com/recipe"}
        )
        assert res.status_code == 200
        body = res.json()
        assert body["name"] == "Test Recipe"
        assert body["servings"] == 2.0
        assert body["ingredients"] == []
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_import_recipe_requires_auth():
    client = TestClient(app)
    res = client.post("/recipes/import", json={"url": "https://example.com/recipe"})
    assert res.status_code in (401, 403)
