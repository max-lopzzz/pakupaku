import asyncio
import uuid

from auth import get_current_user, hash_password
from database import get_db
from main import app
from models import User
import main


async def _make_user(db_session, *, is_admin=False, email=None):
    user = User(
        id=uuid.uuid4(),
        email=email or f"{uuid.uuid4()}@example.com",
        username=f"user{uuid.uuid4().hex[:8]}",
        hashed_password=hash_password("TestPass123!"),
        email_verified=True,
        safe_mode=False,
        uses_custom_goals=False,
        is_admin=is_admin,
    )
    db_session.add(user)
    await db_session.flush()
    return user


def _as(client, user):
    app.dependency_overrides[get_current_user] = lambda: user
    return client


def test_discover_requires_admin(client, db_session):
    user = asyncio.get_event_loop().run_until_complete(_make_user(db_session))
    try:
        res = _as(client, user).post(
            "/recipes/bulk-import/discover", json={"url": "https://example.com/blog"}
        )
        assert res.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_discover_returns_links_for_admin(client, db_session, monkeypatch):
    admin = asyncio.get_event_loop().run_until_complete(
        _make_user(db_session, is_admin=True)
    )

    async def fake_discover(url):
        assert url == "https://example.com/blog"
        return ["https://example.com/blog/recipe-1", "https://example.com/blog/recipe-2"]

    monkeypatch.setattr(main, "discover_recipe_links", fake_discover)
    try:
        res = _as(client, admin).post(
            "/recipes/bulk-import/discover", json={"url": "https://example.com/blog"}
        )
        assert res.status_code == 200
        assert res.json()["urls"] == [
            "https://example.com/blog/recipe-1", "https://example.com/blog/recipe-2",
        ]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_extract_requires_admin(client, db_session):
    user = asyncio.get_event_loop().run_until_complete(_make_user(db_session))
    try:
        res = _as(client, user).post(
            "/recipes/bulk-import/extract", json={"urls": ["https://example.com/a"]}
        )
        assert res.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_extract_returns_drafts_for_admin(client, db_session, monkeypatch):
    from schemas import RecipeImportDraft

    admin = asyncio.get_event_loop().run_until_complete(
        _make_user(db_session, is_admin=True)
    )

    async def fake_extract(urls):
        assert urls == ["https://example.com/a", "https://example.com/b"]
        return [
            RecipeImportDraft(
                name="A", servings=1.0, image_url=None,
                ingredients=[], source_url="https://example.com/a",
            ),
        ]

    monkeypatch.setattr(main, "bulk_extract_drafts", fake_extract)
    try:
        res = _as(client, admin).post(
            "/recipes/bulk-import/extract",
            json={"urls": ["https://example.com/a", "https://example.com/b"]},
        )
        assert res.status_code == 200
        drafts = res.json()["drafts"]
        assert len(drafts) == 1
        assert drafts[0]["name"] == "A"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_extract_empty_result_when_nothing_found(client, db_session, monkeypatch):
    admin = asyncio.get_event_loop().run_until_complete(
        _make_user(db_session, is_admin=True)
    )

    async def fake_extract(urls):
        return []

    monkeypatch.setattr(main, "bulk_extract_drafts", fake_extract)
    try:
        res = _as(client, admin).post(
            "/recipes/bulk-import/extract", json={"urls": ["https://example.com/a"]}
        )
        assert res.status_code == 200
        assert res.json()["drafts"] == []
    finally:
        app.dependency_overrides.pop(get_current_user, None)
