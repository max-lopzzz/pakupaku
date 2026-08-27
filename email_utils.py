"""
email_utils.py
--------------
Async email sending for PakuPaku via Resend's HTTPS API.

Previously used aiosmtplib to talk to smtp.gmail.com directly. Switched
because several common hosts (Render's free tier among them) block
outbound SMTP on all the usual ports (25/465/587) to prevent spam abuse
— the connection just times out, no amount of correct credentials fixes
it. Resend's API is plain HTTPS, which isn't blocked.
"""

import httpx
from urllib.parse import quote

from config import (
    BACKEND_PUBLIC_URL,
    FRONTEND_URL,
    RESEND_API_KEY,
    RESEND_FROM_EMAIL,
)

RESEND_API_URL = "https://api.resend.com/emails"


async def _send(to_email: str, subject: str, text: str, html: str) -> None:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            RESEND_API_URL,
            headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
            json={
                "from": RESEND_FROM_EMAIL,
                "to": [to_email],
                "subject": subject,
                "text": text,
                "html": html,
            },
        )
        response.raise_for_status()


async def send_verification_email(to_email: str, token: str) -> None:
    verify_url = f"{BACKEND_PUBLIC_URL}/auth/verify-email?token={quote(token)}"

    text = f"""\
Hi there!

Please verify your PakuPaku account by clicking the link below:

{verify_url}

If you didn't create an account, you can safely ignore this email.

— PakuPaku
"""

    html = f"""\
<html><body style="font-family:sans-serif;background:#fcf9ea;padding:2rem;">
  <div style="max-width:480px;margin:0 auto;background:#fff;border-radius:16px;
              border:2px solid #badfdb;padding:2rem;">
    <h2 style="color:#3a2a2a;">Verify your email 🐾</h2>
    <p style="color:#8a6060;">Thanks for signing up for PakuPaku!
       Click the button below to verify your email address.</p>
    <a href="{verify_url}"
       style="display:inline-block;margin-top:1rem;padding:0.85rem 1.5rem;
              background:#badfdb;color:#3a2a2a;border-radius:12px;
              text-decoration:none;font-weight:700;">
      Verify my account
    </a>
    <p style="margin-top:1.5rem;font-size:0.8rem;color:#c8b4b4;">
      If you didn't create an account you can safely ignore this email.
    </p>
  </div>
</body></html>
"""

    await _send(to_email, "Verify your PakuPaku account", text, html)


async def send_password_reset_email(to_email: str, token: str) -> None:
    # Points at the frontend, not the backend — resetting a password needs
    # the user to type a new one, so this can't be a simple GET-and-redirect
    # the way email verification is.
    reset_url = f"{FRONTEND_URL}/?reset={quote(token)}"

    text = f"""\
Hi there!

We received a request to reset your PakuPaku password. Click the link
below to choose a new one:

{reset_url}

This link expires in 1 hour. If you didn't request this, you can
safely ignore this email — your password won't be changed.

— PakuPaku
"""

    html = f"""\
<html><body style="font-family:sans-serif;background:#fcf9ea;padding:2rem;">
  <div style="max-width:480px;margin:0 auto;background:#fff;border-radius:16px;
              border:2px solid #badfdb;padding:2rem;">
    <h2 style="color:#3a2a2a;">Reset your password 🔑</h2>
    <p style="color:#8a6060;">We received a request to reset your PakuPaku
       password. Click the button below to choose a new one.</p>
    <a href="{reset_url}"
       style="display:inline-block;margin-top:1rem;padding:0.85rem 1.5rem;
              background:#badfdb;color:#3a2a2a;border-radius:12px;
              text-decoration:none;font-weight:700;">
      Reset my password
    </a>
    <p style="margin-top:1.5rem;font-size:0.8rem;color:#c8b4b4;">
      This link expires in 1 hour. If you didn't request this, you can
      safely ignore this email — your password won't be changed.
    </p>
  </div>
</body></html>
"""

    await _send(to_email, "Reset your PakuPaku password", text, html)
