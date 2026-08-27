"""
email_utils.py
--------------
Async email sending for PakuPaku using aiosmtplib.
"""

import aiosmtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from urllib.parse import quote

from config import (
    BACKEND_PUBLIC_URL,
    FRONTEND_URL,
    SMTP_FROM,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_USER,
)


async def send_verification_email(to_email: str, token: str) -> None:
    verify_url = f"{BACKEND_PUBLIC_URL}/auth/verify-email?token={quote(token)}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Verify your PakuPaku account"
    msg["From"]    = SMTP_FROM
    msg["To"]      = to_email

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

    msg.attach(MIMEText(text, "plain"))
    msg.attach(MIMEText(html, "html"))

    async with aiosmtplib.SMTP(
        hostname=SMTP_HOST,
        port=SMTP_PORT,
        username=SMTP_USER,
        password=SMTP_PASSWORD,
        start_tls=True,
    ) as smtp:
        await smtp.send_message(msg)


async def send_password_reset_email(to_email: str, token: str) -> None:
    # Points at the frontend, not the backend — resetting a password needs
    # the user to type a new one, so this can't be a simple GET-and-redirect
    # the way email verification is.
    reset_url = f"{FRONTEND_URL}/?reset={quote(token)}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Reset your PakuPaku password"
    msg["From"]    = SMTP_FROM
    msg["To"]      = to_email

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

    msg.attach(MIMEText(text, "plain"))
    msg.attach(MIMEText(html, "html"))

    async with aiosmtplib.SMTP(
        hostname=SMTP_HOST,
        port=SMTP_PORT,
        username=SMTP_USER,
        password=SMTP_PASSWORD,
        start_tls=True,
    ) as smtp:
        await smtp.send_message(msg)
