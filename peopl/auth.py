"""Closed-loop sign-in: a 6-digit code sent to a university email address.

No email address is stored. Each address becomes a keyed hash (HMAC with the
app secret), so a copy of the database does not reveal who is a member.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import time

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.exc import IntegrityError

from .db import claims, login_codes, posts, replies, reports, sessions, users

CODE_TTL = 10 * 60
MAX_ATTEMPTS = 5
MAX_CODES_PER_HOUR = 5
SESSION_TTL = 30 * 24 * 3600

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_NICK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._-]{1,23}$")


class AuthError(RuntimeError):
    """Raised with a message that is safe to show to a person."""


def _now(now) -> int:
    return int(time.time()) if now is None else int(now)


def _mac(value: str, pepper: str) -> str:
    return hmac.new(pepper.encode(), value.encode(), hashlib.sha256).hexdigest()


def normalize_email(raw: str | None) -> str | None:
    email = (raw or "").strip().lower()
    return email if len(email) <= 200 and _EMAIL.match(email) else None


def domain_allowed(email: str, domains) -> bool:
    host = email.rsplit("@", 1)[-1]
    return any(host == d or host.endswith("." + d) for d in domains)


def hash_email(email: str, pepper: str) -> str:
    return _mac("email:" + email, pepper)


def _code_hash(email_hash: str, code: str, pepper: str) -> str:
    return _mac(f"code:{email_hash}:{code}", pepper)


# ---------------------------------------------------------------- codes


def request_code(engine, raw_email, *, pepper, domains, send, now=None) -> str:
    """Create a code and pass it to send(email, code). Returns the email hash."""
    t = _now(now)
    email = normalize_email(raw_email)
    if email is None:
        raise AuthError("Enter your full email address.")
    if not domain_allowed(email, domains):
        raise AuthError("Peopl is only for people with a " + " or ".join(domains) + " email.")
    h = hash_email(email, pepper)
    with engine.begin() as conn:
        banned = conn.execute(select(users.c.banned).where(users.c.email_hash == h)).scalar()
        recent = conn.execute(
            select(func.count()).select_from(login_codes).where(
                login_codes.c.email_hash == h, login_codes.c.created_at > t - 3600
            )
        ).scalar_one()
        too_many = recent >= MAX_CODES_PER_HOUR
        if not banned and not too_many:
            conn.execute(update(login_codes).where(login_codes.c.email_hash == h).values(expires_at=0))
            code = f"{secrets.randbelow(10**6):06d}"
            conn.execute(
                insert(login_codes).values(
                    email_hash=h,
                    code_hash=_code_hash(h, code, pepper),
                    created_at=t,
                    expires_at=t + CODE_TTL,
                    attempts=0,
                )
            )
    if banned:
        raise AuthError("This email can't sign in.")
    if too_many:
        raise AuthError("Too many codes were requested. Try again in an hour.")
    try:
        send(email, code)
    except AuthError:
        raise
    except Exception as exc:
        raise AuthError("The email could not be sent. Try again in a minute.") from exc
    return h


def verify_code(engine, raw_email, code, *, pepper, now=None) -> str:
    """Check a code. Returns the email hash when it is right."""
    t = _now(now)
    email = normalize_email(raw_email)
    if email is None:
        raise AuthError("Enter your email first.")
    h = hash_email(email, pepper)
    digits = re.sub(r"\D", "", code or "")
    error = None
    with engine.begin() as conn:
        row = conn.execute(
            select(login_codes)
            .where(login_codes.c.email_hash == h, login_codes.c.expires_at > t)
            .order_by(login_codes.c.id.desc())
        ).first()
        if row is None:
            error = "That code has expired. Ask for a new one."
        elif row.attempts >= MAX_ATTEMPTS:
            error = "Too many wrong tries. Ask for a new code."
        else:
            conn.execute(
                update(login_codes).where(login_codes.c.id == row.id).values(attempts=row.attempts + 1)
            )
            if hmac.compare_digest(row.code_hash, _code_hash(h, digits, pepper)):
                conn.execute(update(login_codes).where(login_codes.c.id == row.id).values(expires_at=0))
            else:
                error = "That code is not right."
    if error:
        raise AuthError(error)
    return h


# ---------------------------------------------------------------- users


def _user_dict(row) -> dict:
    return dict(row._mapping)


def get_user_by_hash(engine, email_hash: str) -> dict | None:
    with engine.connect() as conn:
        row = conn.execute(select(users).where(users.c.email_hash == email_hash)).first()
    return _user_dict(row) if row else None


def get_user(engine, user_id: int) -> dict | None:
    with engine.connect() as conn:
        row = conn.execute(select(users).where(users.c.id == user_id)).first()
    return _user_dict(row) if row else None


def create_user(engine, email_hash: str, nickname: str, *, admin_hashes=frozenset(), now=None) -> dict:
    name = " ".join((nickname or "").split())
    if not _NICK.match(name):
        raise AuthError("Pick a nickname with 2 to 24 letters or numbers.")
    try:
        with engine.begin() as conn:
            conn.execute(
                insert(users).values(
                    email_hash=email_hash,
                    nickname=name,
                    nickname_key=name.lower(),
                    created_at=_now(now),
                    is_admin=email_hash in admin_hashes,
                    is_organizer=False,
                    banned=False,
                )
            )
    except IntegrityError as exc:
        raise AuthError("That nickname is taken. Try another one.") from exc
    return get_user_by_hash(engine, email_hash)


def sync_admin(engine, user: dict, is_admin: bool) -> dict:
    if bool(user["is_admin"]) != is_admin:
        with engine.begin() as conn:
            conn.execute(update(users).where(users.c.id == user["id"]).values(is_admin=is_admin))
        user = get_user(engine, user["id"])
    return user


# ---------------------------------------------------------------- sessions


def create_session(engine, user_id: int, *, pepper: str, now=None) -> str:
    token = secrets.token_urlsafe(32)
    with engine.begin() as conn:
        conn.execute(delete(sessions).where(sessions.c.expires_at < _now(now)))
        conn.execute(
            insert(sessions).values(
                token_hash=_mac("session:" + token, pepper),
                user_id=user_id,
                expires_at=_now(now) + SESSION_TTL,
            )
        )
    return token


def get_user_for_token(engine, token: str | None, *, pepper: str, now=None) -> dict | None:
    if not token:
        return None
    with engine.connect() as conn:
        row = conn.execute(
            select(users)
            .select_from(sessions.join(users, users.c.id == sessions.c.user_id))
            .where(sessions.c.token_hash == _mac("session:" + token, pepper), sessions.c.expires_at > _now(now))
        ).first()
    user = _user_dict(row) if row else None
    return user if user and not user["banned"] else None


def sign_out(engine, token: str | None, *, pepper: str) -> None:
    if token:
        with engine.begin() as conn:
            conn.execute(delete(sessions).where(sessions.c.token_hash == _mac("session:" + token, pepper)))


def delete_account(engine, user_id: int) -> None:
    """Remove a person and everything they posted."""
    with engine.begin() as conn:
        mine = [r[0] for r in conn.execute(select(posts.c.id).where(posts.c.user_id == user_id))]
        if mine:
            conn.execute(delete(claims).where(claims.c.post_id.in_(mine)))
            conn.execute(delete(replies).where(replies.c.post_id.in_(mine)))
            conn.execute(delete(reports).where(reports.c.post_id.in_(mine)))
            conn.execute(delete(posts).where(posts.c.id.in_(mine)))
        conn.execute(delete(claims).where(claims.c.user_id == user_id))
        conn.execute(delete(replies).where(replies.c.user_id == user_id))
        conn.execute(delete(reports).where(reports.c.user_id == user_id))
        conn.execute(delete(sessions).where(sessions.c.user_id == user_id))
        conn.execute(delete(users).where(users.c.id == user_id))
