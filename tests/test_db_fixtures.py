import uuid

import pytest
from sqlalchemy import select

from models import User


@pytest.mark.asyncio
async def test_db_session_persists_and_queries(db_session):
    user = User(
        id=uuid.uuid4(),
        email="fixture-smoke@example.com",
        username="fixturesmoke",
        hashed_password="x",
        email_verified=True,
        safe_mode=False,
        uses_custom_goals=False,
    )
    db_session.add(user)
    await db_session.flush()

    result = await db_session.execute(
        select(User).where(User.email == "fixture-smoke@example.com")
    )
    found = result.scalar_one()
    assert found.username == "fixturesmoke"


def test_client_fixture_reaches_the_same_session(client, db_session):
    """A request that queries the DB should see what db_session already
    has, proving the override actually points at the same session."""
    import asyncio
    import uuid as _uuid
    from models import User

    async def _seed():
        u = User(
            id=_uuid.uuid4(),
            email="client-fixture@example.com",
            username="clientfixture",
            # A real bcrypt hash (of a different password than what the
            # test sends) is required here: passlib's bcrypt scheme
            # raises UnknownHashError on an unparseable hash like "x"
            # instead of returning False, which would surface as a 500
            # rather than the 401 this test asserts.
            hashed_password="$2b$12$jwoyI6XDTRjuC2ZCjEbk7e98nGaXhKTjZWCZ0817Wk7t03sXwmTQO",
            email_verified=True,
            safe_mode=False,
            uses_custom_goals=False,
        )
        db_session.add(u)
        await db_session.flush()

    asyncio.get_event_loop().run_until_complete(_seed())

    # /auth/login with a wrong password against a real seeded user
    # proves the request reached the same DB — a 401 (bad password)
    # rather than some other error confirms the user was actually found.
    res = client.post(
        "/auth/login",
        json={"email": "client-fixture@example.com", "password": "wrong"},
    )
    assert res.status_code == 401
