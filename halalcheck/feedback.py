"""Feedback logging. Never stores photos, names or locations.

Local files vanish when a free host restarts, so set FEEDBACK_WEBHOOK_URL to a
Google Apps Script web app (see README) to keep reports in a Google Sheet.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import requests

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "feedback.jsonl"
ALLOWED = ("source", "verdict", "rule_ids", "product_code", "reason", "comment", "rulebook_version")
REASONS = (
    "Said not halal but it is halal",
    "Said halal but it is not",
    "Wrong product or wrong ingredients",
    "Missing information",
    "Other",
)


def _clip(value, limit=500):
    if isinstance(value, (list, tuple)):
        return [str(v)[:80] for v in value][:30]
    return str(value)[:limit] if value is not None else ""


def log_feedback(entry: dict, path: Path | str | None = None, webhook: str | None = None) -> bool:
    record = {k: _clip(entry.get(k)) for k in ALLOWED if k in entry}
    record["time"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    saved = False
    target = Path(path or os.getenv("FEEDBACK_PATH") or DEFAULT_PATH)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        saved = True
    except OSError:
        pass
    url = webhook or os.getenv("FEEDBACK_WEBHOOK_URL")
    if url:
        try:
            response = requests.post(url, json=record, timeout=5)
            saved = saved or response.ok
        except requests.RequestException:
            pass
    return saved
