"""Settings read from Streamlit secrets or environment variables."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .auth import hash_email, normalize_email

DEV_PEPPER = "dev-only-secret-change-me"


@dataclass(frozen=True)
class Settings:
    pepper: str
    pepper_is_default: bool
    domains: tuple[str, ...]
    admin_hashes: frozenset[str]
    dev_show_code: bool
    database_url: str | None


def load_settings(get: Callable[[str], str]) -> Settings:
    pepper = get("APP_SECRET") or DEV_PEPPER
    domains = tuple(
        d.strip().lower().lstrip("@")
        for d in (get("ALLOWED_DOMAINS") or "uchicago.edu").split(",")
        if d.strip()
    )
    admins = set()
    for raw in (get("ADMIN_EMAILS") or "").split(","):
        email = normalize_email(raw)
        if email:
            admins.add(hash_email(email, pepper))
    return Settings(
        pepper=pepper,
        pepper_is_default=pepper == DEV_PEPPER,
        domains=domains,
        admin_hashes=frozenset(admins),
        dev_show_code=(get("DEV_SHOW_CODE") or "").strip().lower() in ("1", "true", "yes"),
        database_url=get("DATABASE_URL") or None,
    )
