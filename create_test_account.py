"""
create_test_account.py
----------------------
Creates a pre-verified Google Play reviewer test account.

Run once against your production (or staging) database:

    python create_test_account.py

The account will be created with email_verified=True so reviewers
never hit the email verification wall.

Edit TEST_EMAIL / TEST_PASSWORD / TEST_USERNAME below before running.
"""

import asyncio
import uuid

import bcrypt
from sqlalchemy.future import select

from database import AsyncSessionLocal
from models import User

# ── Configure your test account here ─────────────────────────────────────────

TEST_EMAIL    = "googleplay.reviewer@pakupaku.app"   # change to whatever you like
TEST_USERNAME = "gplay_reviewer"
TEST_PASSWORD = "PakuReview26!"                      # max 72 chars for bcrypt


def _hash(plain: str) -> str:
    """Hash with bcrypt directly, bypassing passlib version issues."""
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()

# ─────────────────────────────────────────────────────────────────────────────


async def create_test_account() -> None:
    async with AsyncSessionLocal() as session:
        # Check if the account already exists
        result = await session.execute(
            select(User).where(User.email == TEST_EMAIL)
        )
        existing = result.scalar_one_or_none()

        if existing is not None:
            # If it exists but isn't verified, fix that
            if not existing.email_verified:
                existing.email_verified    = True
                existing.verification_token = None
                await session.commit()
                print(f"✓ Account already existed — marked as verified: {TEST_EMAIL}")
            else:
                print(f"✓ Account already exists and is verified: {TEST_EMAIL}")
            return

        user = User(
            id                 = uuid.uuid4(),
            email              = TEST_EMAIL,
            username           = TEST_USERNAME,
            hashed_password    = _hash(TEST_PASSWORD),
            email_verified     = True,       # pre-verified — no email needed
            verification_token = None,
        )

        session.add(user)
        await session.commit()

        print("✓ Test account created successfully")
        print(f"  Email:    {TEST_EMAIL}")
        print(f"  Username: {TEST_USERNAME}")
        print(f"  Password: {TEST_PASSWORD}")
        print(f"  Verified: True")


if __name__ == "__main__":
    asyncio.run(create_test_account())
