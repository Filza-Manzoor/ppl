"""Deterministic halal rule engine.

Photos and models only supply text. Every verdict in this app comes from the
rules in data/rules.json, so nothing printed on a pack or hidden in a photo can
talk the app into an answer.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable

RULES_PATH = Path(__file__).parent / "data" / "rules.json"

NOT_HALAL = "not_halal"
DOUBTFUL = "doubtful"
LOOKS_HALAL = "looks_halal"
UNKNOWN = "unknown"

# Higher means more serious. "ok" rules only exist to cancel false alarms.
SEVERITY = {"prohibited": 3, "doubtful": 2, "check": 1, "ok": 0}

DISH_QUESTIONS = (
    "Is the meat halal certified, and who supplies it?",
    "Do any sauces, marinades or desserts contain alcohol, wine or beer?",
    "Is the food cooked in oil or on a grill that is shared with pork?",
)

GENERAL_NOTE = (
    "No flagged ingredients were found in the list. Recipes change between "
    "countries and batches, so check the pack in your hand."
)


@dataclass(frozen=True)
class Rule:
    id: str
    label: str
    status: str
    pattern: re.Pattern
    reason: str
    note: str = ""
    question: str = ""
    cleared_by_claim: bool = False


@dataclass(frozen=True)
class Rulebook:
    version: str
    rules: tuple[Rule, ...]


@dataclass(frozen=True)
class Match:
    rule_id: str
    label: str
    status: str
    text: str
    reason: str
    note: str
    question: str
    cleared: bool


@dataclass(frozen=True)
class Analysis:
    verdict: str
    headline: str
    matches: tuple[Match, ...]
    verify: tuple[str, ...]
    notes: tuple[str, ...]
    basis: str  # "ingredients", "claim", "dish" or "none"


# ---------------------------------------------------------------- loading


@lru_cache(maxsize=4)
def load_rulebook(path: Path = RULES_PATH) -> Rulebook:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    rules: list[Rule] = []
    seen: set[str] = set()
    for item in raw["rules"]:
        for key in ("id", "label", "status", "pattern", "reason"):
            if not item.get(key):
                raise ValueError(f"Rule is missing '{key}': {item}")
        if item["status"] not in SEVERITY:
            raise ValueError(f"Rule {item['id']} has unknown status {item['status']!r}")
        if item["id"] in seen:
            raise ValueError(f"Duplicate rule id {item['id']!r}")
        seen.add(item["id"])
        rules.append(
            Rule(
                id=item["id"],
                label=item["label"],
                status=item["status"],
                pattern=re.compile(item["pattern"], re.IGNORECASE),
                reason=item["reason"],
                note=item.get("note", ""),
                question=item.get("question", ""),
                cleared_by_claim=bool(item.get("cleared_by_claim", False)),
            )
        )
    return Rulebook(version=str(raw.get("version", "0")), rules=tuple(rules))


def raw_rules(path: Path = RULES_PATH) -> list[dict]:
    """The rule dictionaries as written in the JSON file (used by tests)."""
    return json.loads(Path(path).read_text(encoding="utf-8"))["rules"]


# ---------------------------------------------------------------- text prep

_E_NUMBER = re.compile(r"\be[\s-]?(\d{3,4}[a-z]?)\b")


def normalize_text(text: str) -> str:
    text = (text or "").lower()
    text = text.replace("’", "'").replace("‘", "'")
    text = re.sub(r"\s+", " ", text)
    return _E_NUMBER.sub(r"e\1", text).strip()


def tags_to_text(tags: Iterable[str] | None) -> str:
    """Turn Open Food Facts tags such as 'en:pork-fat' into 'pork fat'."""
    words = []
    for tag in tags or ():
        name = re.sub(r"^[a-z]{2,3}:", "", str(tag).lower())
        words.append(name.replace("-", " ").strip())
    return ", ".join(w for w in words if w)


def detect_halal_claim(labels_tags: Iterable[str] | None = (), text: str = "") -> bool:
    """True when the data says the product carries a halal label."""
    for tag in labels_tags or ():
        name = str(tag).split(":")[-1].lower().replace("-", " ")
        if "halal" in name and not re.search(r"\b(non|not) halal\b", name):
            return True
    cleaned = normalize_text(text)
    return bool(re.search(r"\b(halal[- ]certified|certified halal|halal certification)\b", cleaned))


# ---------------------------------------------------------------- matching


def find_matches(text: str, rulebook: Rulebook | None = None) -> list[tuple[Rule, str]]:
    """Return non-overlapping matches. The longest match wins, so
    'ginger beer' cancels 'beer' and 'fish gelatin' cancels 'gelatin'."""
    rulebook = rulebook or load_rulebook()
    candidates = []
    for rule in rulebook.rules:
        for found in rule.pattern.finditer(text):
            if found.end() > found.start():
                candidates.append((found.start(), found.end(), rule, found.group(0)))
    candidates.sort(key=lambda c: (-(c[1] - c[0]), -SEVERITY[c[2].status], c[0]))

    taken: list[tuple[int, int]] = []
    accepted = []
    for start, end, rule, matched in candidates:
        if any(start < t_end and end > t_start for t_start, t_end in taken):
            continue
        taken.append((start, end))
        accepted.append((start, rule, matched))
    accepted.sort(key=lambda a: a[0])

    result: list[tuple[Rule, str]] = []
    seen: set[tuple[str, str]] = set()
    for _, rule, matched in accepted:
        key = (rule.id, matched.lower())
        if key in seen:
            continue
        seen.add(key)
        result.append((rule, matched))
    return result


def _unique(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


# ---------------------------------------------------------------- verdicts


def analyze(
    text: str = "",
    *,
    tags: Iterable[str] | None = (),
    additives: Iterable[str] | None = (),
    halal_claim: bool = False,
    mode: str = "ingredients",
    rulebook: Rulebook | None = None,
) -> Analysis:
    """Check ingredient text (plus optional database tags) against the rulebook.

    mode="dish" is for guesses made from a photo of a plated meal. A photo can
    never show how food was sourced, so a dish is never given a halal verdict.
    """
    rulebook = rulebook or load_rulebook()
    dish = mode == "dish"
    claim = bool(halal_claim) and not dish

    parts = [text or "", tags_to_text(tags), tags_to_text(additives)]
    combined = normalize_text(". ".join(p for p in parts if p.strip()))
    if not combined.strip(" .,;"):
        return Analysis(
            verdict=UNKNOWN,
            headline="Can't tell: there is no ingredient list to check",
            matches=(),
            verify=("Take a clear photo of the ingredient list on the pack.",),
            notes=(),
            basis="none",
        )

    matches: list[Match] = []
    for rule, matched in find_matches(combined, rulebook):
        cleared = claim and rule.cleared_by_claim and rule.status == "doubtful"
        matches.append(
            Match(
                rule_id=rule.id,
                label=rule.label,
                status=rule.status,
                text=matched,
                reason=rule.reason,
                note=rule.note,
                question=rule.question,
                cleared=cleared,
            )
        )

    prohibited = [m for m in matches if m.status == "prohibited"]
    doubtful = [m for m in matches if m.status == "doubtful" and not m.cleared]
    notes: list[str] = []

    if prohibited:
        verdict = NOT_HALAL
        found = _unique(m.text.lower() for m in prohibited)
        prefix = "Not halal if the dish contains" if dish else "Not halal: found"
        headline = f"{prefix} {', '.join(found[:3])}" + (" and more" if len(found) > 3 else "")
        if claim:
            notes.append(
                "The data says this product is halal, but the ingredients include "
                "a prohibited item. Treat the data as conflicting and check the pack."
            )
    elif doubtful or dish:
        verdict = DOUBTFUL
        count = len(_unique(m.label for m in doubtful))
        if dish:
            headline = "A photo can't show halal status. Ask the questions below."
        else:
            headline = f"Doubtful: {count} thing{'s' if count != 1 else ''} to check"
    else:
        verdict = LOOKS_HALAL
        if claim:
            headline = "Claims to be halal. Check the logo on the pack."
        else:
            headline = "Looks halal from the ingredient list. Check the pack."
            notes.append(GENERAL_NOTE)

    verify: list[str] = []
    if verdict != NOT_HALAL:
        for m in matches:
            if m.status in ("doubtful", "check") and not m.cleared:
                verify.append(m.question)
    if claim and verdict == LOOKS_HALAL:
        verify.append("Look for the halal logo on the pack and check who issues it.")
    if dish:
        verify.extend(DISH_QUESTIONS)

    return Analysis(
        verdict=verdict,
        headline=headline,
        matches=tuple(matches),
        verify=tuple(_unique(verify)),
        notes=tuple(notes),
        basis="dish" if dish else ("claim" if claim and verdict == LOOKS_HALAL else "ingredients"),
    )
