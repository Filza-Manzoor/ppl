"""Plates, events, replies, claims and moderation."""
from __future__ import annotations

import time

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.exc import IntegrityError

from . import copy
from .db import claims, posts, replies, reports, sessions, users

DAILY_POST_LIMIT = 6
DAILY_CLAIM_LIMIT = 4
DAILY_REPLY_LIMIT = 30
GRACE = 3 * 3600  # keep ended plates visible for a while, so people see "All shared"

PLATE, EVENT = "plate", "event"


class PostError(RuntimeError):
    """Raised with a message that is safe to show to a person."""


def _now(now) -> int:
    return int(time.time()) if now is None else int(now)


def _text(value, label: str, low: int, high: int) -> str:
    lines = [" ".join(line.split()) for line in (value or "").strip().splitlines()]
    text = "\n".join(line for line in lines if line)
    if len(text) < low:
        raise PostError(f"Please add {label}.")
    if len(text) > high:
        raise PostError(f"{label[0].upper() + label[1:]} is too long. Keep it under {high} characters.")
    return text


def _check_user(user: dict) -> None:
    if not user or user.get("banned"):
        raise PostError("This account can't post.")


def _count_since(conn, table, user_col, user_id, seconds, now) -> int:
    return conn.execute(
        select(func.count()).select_from(table).where(user_col == user_id, table.c.created_at > now - seconds)
    ).scalar_one()


# ---------------------------------------------------------------- creating


def create_plate(engine, user, *, body, portions, place, minutes, ingredients, tag, safe_ok, now=None) -> int:
    t = _now(now)
    _check_user(user)
    if not safe_ok:
        raise PostError("Please confirm the food was packed and stored safely.")
    body = _text(body, "a message", 3, 400)
    place = _text(place, "a pickup place", 2, 80)
    ingredients = _text(ingredients, "the ingredients and allergens", 2, 300)
    if tag not in copy.TAGS:
        raise PostError("Pick where the food came from.")
    if not 1 <= int(portions) <= 50:
        raise PostError("Portions must be between 1 and 50.")
    if not 15 <= int(minutes) <= 1440:
        raise PostError("Pick how long the food is available.")
    with engine.begin() as conn:
        if _count_since(conn, posts, posts.c.user_id, user["id"], 86400, t) >= DAILY_POST_LIMIT:
            raise PostError("That's a lot of sharing today. Try again tomorrow.")
        result = conn.execute(
            insert(posts).values(
                user_id=user["id"],
                kind=PLATE,
                body=body,
                portions_total=int(portions),
                portions_left=int(portions),
                place=place,
                ingredients=ingredients,
                tag=tag,
                when_ts=t + int(minutes) * 60,
                status="open",
                created_at=t,
            )
        )
        return result.inserted_primary_key[0]


def create_event(engine, user, *, title, body, starts_at, place, now=None) -> int:
    t = _now(now)
    _check_user(user)
    if not (user.get("is_organizer") or user.get("is_admin")):
        raise PostError("Events are posted by organizers. Ask an admin to add you.")
    title = _text(title, "an event name", 3, 100)
    body = _text(body, "a few details", 3, 400)
    place = _text(place, "a place", 2, 80)
    if starts_at < t - 3600:
        raise PostError("That start time has already passed.")
    with engine.begin() as conn:
        result = conn.execute(
            insert(posts).values(
                user_id=user["id"],
                kind=EVENT,
                title=title,
                body=body,
                portions_total=0,
                portions_left=0,
                place=place,
                when_ts=int(starts_at),
                status="open",
                created_at=t,
            )
        )
        return result.inserted_primary_key[0]


# ---------------------------------------------------------------- reading


def _rows(conn, stmt):
    return [dict(r._mapping) for r in conn.execute(stmt)]


def list_plates(engine, *, now=None, limit=50) -> list[dict]:
    t = _now(now)
    stmt = (
        select(posts, users.c.nickname)
        .select_from(posts.join(users, users.c.id == posts.c.user_id))
        .where(posts.c.kind == PLATE, posts.c.status != "hidden", posts.c.when_ts > t - GRACE)
        .order_by(posts.c.created_at.desc())
        .limit(limit)
    )
    with engine.connect() as conn:
        items = _rows(conn, stmt)
        counts = dict(
            conn.execute(
                select(claims.c.post_id, func.count()).where(claims.c.post_id.in_([p["id"] for p in items] or [0])).group_by(claims.c.post_id)
            ).all()
        )
    for p in items:
        p["claims_count"] = counts.get(p["id"], 0)
        live = p["status"] == "open" and p["when_ts"] > t and p["portions_left"] > 0
        p["state"] = "open" if live else "shared" if (p["portions_left"] == 0 or p["status"] == "closed") else "ended"
    items.sort(key=lambda p: (p["state"] != "open", -p["created_at"]))
    return items


def list_events(engine, *, now=None, limit=50) -> list[dict]:
    t = _now(now)
    stmt = (
        select(posts, users.c.nickname)
        .select_from(posts.join(users, users.c.id == posts.c.user_id))
        .where(posts.c.kind == EVENT, posts.c.status != "hidden", posts.c.when_ts > t - GRACE)
        .order_by(posts.c.when_ts.asc())
        .limit(limit)
    )
    with engine.connect() as conn:
        return _rows(conn, stmt)


def my_claims(engine, user_id: int) -> dict[int, dict]:
    with engine.connect() as conn:
        rows = _rows(conn, select(claims).where(claims.c.user_id == user_id))
    return {r["post_id"]: r for r in rows}


def list_claimers(engine, post_id: int) -> list[dict]:
    stmt = (
        select(users.c.nickname, claims.c.rating, claims.c.note, claims.c.created_at)
        .select_from(claims.join(users, users.c.id == claims.c.user_id))
        .where(claims.c.post_id == post_id)
        .order_by(claims.c.created_at)
    )
    with engine.connect() as conn:
        return _rows(conn, stmt)


# ---------------------------------------------------------------- claims


def claim(engine, user, post_id: int, *, now=None) -> None:
    t = _now(now)
    _check_user(user)
    with engine.begin() as conn:
        post = conn.execute(select(posts).where(posts.c.id == post_id)).first()
        if post is None or post.kind != PLATE or post.status != "open":
            raise PostError("This plate is no longer available.")
        if post.user_id == user["id"]:
            raise PostError("This is your own plate.")
        if post.when_ts <= t:
            raise PostError("The pickup time has passed.")
        if post.portions_left <= 0:
            raise PostError("All shared. Thanks for asking!")
        if _count_since(conn, claims, claims.c.user_id, user["id"], 86400, t) >= DAILY_CLAIM_LIMIT:
            raise PostError("You've asked for a few plates today. Try again tomorrow.")
        took = conn.execute(
            update(posts).where(posts.c.id == post_id, posts.c.portions_left > 0).values(portions_left=posts.c.portions_left - 1)
        )
        if took.rowcount != 1:
            raise PostError("All shared. Thanks for asking!")
        try:
            with conn.begin_nested():
                conn.execute(insert(claims).values(post_id=post_id, user_id=user["id"], created_at=t))
        except IntegrityError as exc:
            raise PostError("You already asked for this one.") from exc


def unclaim(engine, user, post_id: int) -> None:
    with engine.begin() as conn:
        gone = conn.execute(delete(claims).where(claims.c.post_id == post_id, claims.c.user_id == user["id"]))
        if gone.rowcount:
            conn.execute(update(posts).where(posts.c.id == post_id).values(portions_left=posts.c.portions_left + 1))


def rate_claim(engine, user, post_id: int, rating: str, note: str = "") -> None:
    if rating not in copy.RATINGS:
        raise PostError("Pick one of the options.")
    note = " ".join((note or "").split())[:200]
    with engine.begin() as conn:
        done = conn.execute(
            update(claims).where(claims.c.post_id == post_id, claims.c.user_id == user["id"]).values(rating=rating, note=note or None)
        )
        if done.rowcount != 1:
            raise PostError("You can rate a plate after you ask for it.")


def close_post(engine, user, post_id: int) -> None:
    with engine.begin() as conn:
        done = conn.execute(
            update(posts).where(posts.c.id == post_id, posts.c.user_id == user["id"]).values(status="closed")
        )
        if done.rowcount != 1:
            raise PostError("Only the person who posted can close this.")


# ---------------------------------------------------------------- replies


def add_reply(engine, user, post_id: int, body: str, *, now=None) -> None:
    t = _now(now)
    _check_user(user)
    body = _text(body, "a message", 1, 300)
    with engine.begin() as conn:
        post = conn.execute(select(posts.c.id, posts.c.status).where(posts.c.id == post_id)).first()
        if post is None or post.status == "hidden":
            raise PostError("This post is no longer there.")
        if _count_since(conn, replies, replies.c.user_id, user["id"], 86400, t) >= DAILY_REPLY_LIMIT:
            raise PostError("Lots of chatting today. Try again tomorrow.")
        conn.execute(insert(replies).values(post_id=post_id, user_id=user["id"], body=body, created_at=t))


def list_replies(engine, post_id: int, limit: int = 20) -> list[dict]:
    stmt = (
        select(users.c.nickname, replies.c.body, replies.c.created_at)
        .select_from(replies.join(users, users.c.id == replies.c.user_id))
        .where(replies.c.post_id == post_id)
        .order_by(replies.c.created_at.asc())
        .limit(limit)
    )
    with engine.connect() as conn:
        return _rows(conn, stmt)


# ---------------------------------------------------------------- moderation


def report_post(engine, user, post_id: int, reason: str, *, now=None) -> None:
    reason = _text(reason, "a short reason", 3, 200)
    try:
        with engine.begin() as conn:
            conn.execute(insert(reports).values(post_id=post_id, user_id=user["id"], reason=reason, created_at=_now(now), resolved=False))
    except IntegrityError as exc:
        raise PostError("You already reported this one. Thank you.") from exc


def _need_admin(admin: dict) -> None:
    if not admin or not admin.get("is_admin"):
        raise PostError("Only admins can do that.")


def list_reports(engine, admin: dict) -> list[dict]:
    _need_admin(admin)
    stmt = (
        select(
            reports.c.id.label("report_id"),
            reports.c.reason,
            posts.c.id.label("post_id"),
            posts.c.body,
            posts.c.user_id.label("author_id"),
            users.c.nickname.label("author"),
        )
        .select_from(reports.join(posts, posts.c.id == reports.c.post_id).join(users, users.c.id == posts.c.user_id))
        .where(reports.c.resolved.is_(False))
        .order_by(reports.c.created_at)
    )
    with engine.connect() as conn:
        return _rows(conn, stmt)


def hide_post(engine, admin: dict, post_id: int) -> None:
    _need_admin(admin)
    with engine.begin() as conn:
        conn.execute(update(posts).where(posts.c.id == post_id).values(status="hidden"))
        conn.execute(update(reports).where(reports.c.post_id == post_id).values(resolved=True))


def dismiss_report(engine, admin: dict, report_id: int) -> None:
    _need_admin(admin)
    with engine.begin() as conn:
        conn.execute(update(reports).where(reports.c.id == report_id).values(resolved=True))


def ban_user(engine, admin: dict, user_id: int) -> None:
    _need_admin(admin)
    with engine.begin() as conn:
        target = conn.execute(select(users.c.is_admin).where(users.c.id == user_id)).first()
        if target is None:
            raise PostError("That person was not found.")
        if target.is_admin:
            raise PostError("Admins can't be banned.")
        conn.execute(update(users).where(users.c.id == user_id).values(banned=True))
        conn.execute(delete(sessions).where(sessions.c.user_id == user_id))
        conn.execute(update(posts).where(posts.c.user_id == user_id).values(status="hidden"))
        conn.execute(update(reports).where(reports.c.post_id.in_(select(posts.c.id).where(posts.c.user_id == user_id))).values(resolved=True))


def set_organizer(engine, admin: dict, nickname: str, value: bool) -> None:
    _need_admin(admin)
    with engine.begin() as conn:
        done = conn.execute(update(users).where(users.c.nickname_key == (nickname or "").strip().lower()).values(is_organizer=value))
        if done.rowcount != 1:
            raise PostError("No one has that nickname.")
