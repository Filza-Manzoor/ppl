"""Friendly times in Chicago time."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Chicago")


def local(ts: int) -> datetime:
    return datetime.fromtimestamp(ts, TZ)


def _clock(d: datetime) -> str:
    return f"{d.hour % 12 or 12}:{d.minute:02d} {'AM' if d.hour < 12 else 'PM'}"


def until_text(ts: int, now: int) -> str:
    d, today = local(ts), local(now).date()
    days = (d.date() - today).days
    if days == 0:
        return f"until {_clock(d)}"
    if days == 1:
        return f"until tomorrow {_clock(d)}"
    return f"until {d.strftime('%a %b')} {d.day}, {_clock(d)}"


def event_when(ts: int, now: int) -> str:
    d, today = local(ts), local(now).date()
    days = (d.date() - today).days
    if days == 0:
        return f"Today, {_clock(d)}"
    if days == 1:
        return f"Tomorrow, {_clock(d)}"
    return f"{d.strftime('%a %b')} {d.day}, {_clock(d)}"


def ago_text(ts: int, now: int) -> str:
    secs = max(0, now - ts)
    if secs < 90:
        return "just now"
    if secs < 3600:
        return f"{secs // 60} min ago"
    if secs < 86400:
        return f"{secs // 3600} h ago"
    return f"{secs // 86400} d ago"


def to_epoch(date, time_) -> int:
    return int(datetime.combine(date, time_, tzinfo=TZ).timestamp())
