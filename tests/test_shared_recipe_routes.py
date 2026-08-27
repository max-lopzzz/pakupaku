import uuid

from auth import get_current_user, hash_password
from database import get_db
from main import app
from models import User


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


def test_non_admin_cannot_set_is_shared(client, db_session):
    import asyncio
    user = asyncio.get_event_loop().run_until_complete(_make_user(db_session))
    try:
        res = _as(client, user).post(
            "/recipes",
            json={
                "name": "Not actually shared",
                "servings": 1,
                "ingredients": [{"food_name": "rice", "amount_g": 100}],
                "is_shared": True,
            },
        )
        assert res.status_code == 201
        assert res.json()["is_shared"] is False
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_admin_can_set_is_shared(client, db_session):
    import asyncio
    admin = asyncio.get_event_loop().run_until_complete(
        _make_user(db_session, is_admin=True)
    )
    try:
        res = _as(client, admin).post(
            "/recipes",
            json={
                "name": "A real shared recipe",
                "servings": 2,
                "ingredients": [{"food_name": "beans", "amount_g": 200}],
                "is_shared": True,
                "image_url": "https://example.com/beans.jpg",
                "source_url": "https://example.com/beans-recipe",
                "instructions": "Soak beans.\nSimmer 1 hour.",
                "diet_tags": ["vegan", "gluten_free"],
            },
        )
        assert res.status_code == 201
        body = res.json()
        assert body["is_shared"] is True
        assert body["image_url"] == "https://example.com/beans.jpg"
        assert body["source_url"] == "https://example.com/beans-recipe"
        assert body["instructions"] == "Soak beans.\nSimmer 1 hour."
        assert sorted(body["diet_tags"]) == ["gluten_free", "vegan"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_update_recipe_cannot_flip_is_shared_without_admin(client, db_session):
    import asyncio
    user = asyncio.get_event_loop().run_until_complete(_make_user(db_session))
    try:
        c = _as(client, user)
        created = c.post(
            "/recipes",
            json={
                "name": "Mine",
                "servings": 1,
                "ingredients": [{"food_name": "rice", "amount_g": 100}],
            },
        ).json()
        res = c.patch(f"/recipes/{created['id']}", json={"is_shared": True})
        assert res.status_code == 200
        assert res.json()["is_shared"] is False
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_shared_recipes_visible_to_non_owner(client, db_session):
    import asyncio

    async def _setup():
        admin = await _make_user(db_session, is_admin=True)
        viewer = await _make_user(db_session)
        return admin, viewer

    admin, viewer = asyncio.get_event_loop().run_until_complete(_setup())
    try:
        _as(client, admin).post(
            "/recipes",
            json={
                "name": "Shared one",
                "servings": 1,
                "ingredients": [{"food_name": "rice", "amount_g": 100}],
                "is_shared": True,
            },
        )
        _as(client, admin).post(
            "/recipes",
            json={
                "name": "Admin's private recipe",
                "servings": 1,
                "ingredients": [{"food_name": "rice", "amount_g": 100}],
            },
        )

        res = _as(client, viewer).get("/recipes/shared")
        assert res.status_code == 200
        names = [r["name"] for r in res.json()]
        assert names == ["Shared one"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_copy_shared_recipe_is_independent(client, db_session):
    import asyncio

    async def _setup():
        admin = await _make_user(db_session, is_admin=True)
        copier = await _make_user(db_session)
        return admin, copier

    admin, copier = asyncio.get_event_loop().run_until_complete(_setup())
    try:
        original = _as(client, admin).post(
            "/recipes",
            json={
                "name": "Original",
                "servings": 1,
                "ingredients": [{"food_name": "rice", "amount_g": 100}],
                "is_shared": True,
            },
        ).json()

        copy_res = _as(client, copier).post(f"/recipes/{original['id']}/copy")
        assert copy_res.status_code == 201
        copy = copy_res.json()
        assert copy["id"] != original["id"]
        assert copy["name"] == "Original"
        assert copy["is_shared"] is False
        assert copy["user_id"] == str(copier.id)

        # Editing the copy must not touch the original
        _as(client, copier).patch(f"/recipes/{copy['id']}", json={"name": "My version"})
        original_after = _as(client, admin).get(f"/recipes/{original['id']}").json()
        assert original_after["name"] == "Original"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_copy_of_private_recipe_you_dont_own_404s(client, db_session):
    import asyncio

    async def _setup():
        owner = await _make_user(db_session)
        other = await _make_user(db_session)
        return owner, other

    owner, other = asyncio.get_event_loop().run_until_complete(_setup())
    try:
        private = _as(client, owner).post(
            "/recipes",
            json={
                "name": "Private",
                "servings": 1,
                "ingredients": [{"food_name": "rice", "amount_g": 100}],
            },
        ).json()

        res = _as(client, other).post(f"/recipes/{private['id']}/copy")
        assert res.status_code == 404
    finally:
        app.dependency_overrides.pop(get_current_user, None)
