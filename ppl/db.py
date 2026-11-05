"""Database tables. SQLite for local use, Postgres (for example Supabase) online.

The app never stores email addresses. It stores a keyed hash of each address.
"""
from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import (
    Boolean,
    Column,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.pool import StaticPool

DEFAULT_URL = "sqlite:///" + str(Path(__file__).resolve().parent.parent / "data" / "ppl.db")

metadata = MetaData()

users = Table(
    "users",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("email_hash", String(64), nullable=False, unique=True),
    Column("nickname", String(30), nullable=False),
    Column("nickname_key", String(30), nullable=False, unique=True),
    Column("created_at", Integer, nullable=False),
    Column("is_admin", Boolean, nullable=False, default=False),
    Column("is_organizer", Boolean, nullable=False, default=False),
    Column("banned", Boolean, nullable=False, default=False),
)

login_codes = Table(
    "login_codes",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("email_hash", String(64), nullable=False, index=True),
    Column("code_hash", String(64), nullable=False),
    Column("created_at", Integer, nullable=False),
    Column("expires_at", Integer, nullable=False),
    Column("attempts", Integer, nullable=False, default=0),
)

sessions = Table(
    "sessions",
    metadata,
    Column("token_hash", String(64), primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id"), nullable=False, index=True),
    Column("expires_at", Integer, nullable=False),
)

posts = Table(
    "posts",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id"), nullable=False, index=True),
    Column("kind", String(10), nullable=False),  # "plate" or "event"
    Column("title", String(100)),
    Column("body", Text, nullable=False),
    Column("portions_total", Integer, nullable=False, default=0),
    Column("portions_left", Integer, nullable=False, default=0),
    Column("place", String(80), nullable=False),
    Column("ingredients", String(300)),
    Column("tag", String(20)),
    Column("when_ts", Integer, nullable=False),  # plates: pick up until. events: start time.
    Column("status", String(10), nullable=False, default="open"),  # open, closed, hidden
    Column("created_at", Integer, nullable=False),
    Index("ix_posts_kind_when", "kind", "when_ts"),
)

claims = Table(
    "claims",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("post_id", Integer, ForeignKey("posts.id"), nullable=False, index=True),
    Column("user_id", Integer, ForeignKey("users.id"), nullable=False, index=True),
    Column("created_at", Integer, nullable=False),
    Column("rating", String(20)),
    Column("note", String(200)),
    UniqueConstraint("post_id", "user_id", name="uq_claim_once"),
)

replies = Table(
    "replies",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("post_id", Integer, ForeignKey("posts.id"), nullable=False, index=True),
    Column("user_id", Integer, ForeignKey("users.id"), nullable=False, index=True),
    Column("body", String(300), nullable=False),
    Column("created_at", Integer, nullable=False),
)

reports = Table(
    "reports",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("post_id", Integer, ForeignKey("posts.id"), nullable=False, index=True),
    Column("user_id", Integer, ForeignKey("users.id"), nullable=False),
    Column("reason", String(200), nullable=False),
    Column("created_at", Integer, nullable=False),
    Column("resolved", Boolean, nullable=False, default=False),
    UniqueConstraint("post_id", "user_id", name="uq_report_once"),
)


def normalize_url(url: str) -> str:
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg2://" + url[len(prefix):]
    return url


def make_engine(url: str | None = None):
    url = normalize_url(url or os.getenv("DATABASE_URL") or DEFAULT_URL)
    if url.startswith("sqlite"):
        if ":memory:" in url:
            engine = create_engine(url, poolclass=StaticPool, connect_args={"check_same_thread": False})
        else:
            path = url.split("///", 1)[1]
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            engine = create_engine(url, connect_args={"check_same_thread": False})
    else:
        engine = create_engine(url, pool_pre_ping=True)
    metadata.create_all(engine)
    return engine
