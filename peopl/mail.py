"""Send the sign-in code by email through any SMTP account (for example Gmail
with an app password). Set SMTP_HOST, SMTP_USER and SMTP_PASSWORD."""
from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage


def smtp_configured(get=os.getenv) -> bool:
    return all(get(k) for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD"))


def send_code_email(to: str, code: str, get=os.getenv) -> None:
    msg = EmailMessage()
    msg["Subject"] = "Your Peopl sign-in code"
    msg["From"] = get("SMTP_FROM") or get("SMTP_USER")
    msg["To"] = to
    msg.set_content(
        f"Your Peopl code is {code}.\n\n"
        "It works for 10 minutes. If you did not ask for it, you can ignore this email."
    )
    with smtplib.SMTP(get("SMTP_HOST"), int(get("SMTP_PORT") or 587), timeout=15) as server:
        server.starttls()
        server.login(get("SMTP_USER"), get("SMTP_PASSWORD"))
        server.send_message(msg)
