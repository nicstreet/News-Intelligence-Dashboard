from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from datetime import UTC, datetime

from news_intelligence.models import Direction

STOP_WORDS = {
    "a",
    "after",
    "and",
    "as",
    "at",
    "by",
    "for",
    "from",
    "in",
    "into",
    "of",
    "on",
    "the",
    "to",
    "with",
}


def clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def stable_hash(*parts: object, prefix: str = "", length: int = 12) -> str:
    payload = "|".join("" if part is None else str(part) for part in parts)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:length]
    return f"{prefix}{digest}" if prefix else digest


def normalise_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def normalise_text(value: str) -> str:
    clean = normalise_whitespace(value)
    return clean.lower()


def headline_key(value: str) -> str:
    words = re.findall(r"[a-z0-9]+", normalise_text(value))
    useful = [word for word in words if word not in STOP_WORDS]
    return " ".join(useful[:12])


def token_set(value: str) -> set[str]:
    return {
        word
        for word in re.findall(r"[a-z0-9]+", normalise_text(value))
        if word not in STOP_WORDS
    }


def jaccard_similarity(left: Iterable[str], right: Iterable[str]) -> float:
    left_set = set(left)
    right_set = set(right)
    if not left_set and not right_set:
        return 1.0
    if not left_set or not right_set:
        return 0.0
    return len(left_set & right_set) / len(left_set | right_set)


def direction_from_strength(strength: float, *, mixed: bool = False) -> Direction:
    if mixed and abs(strength) <= 0.08:
        return Direction.MIXED
    if strength > 0.08:
        return Direction.BULLISH
    if strength < -0.08:
        return Direction.BEARISH
    if mixed:
        return Direction.MIXED
    return Direction.NEUTRAL


def now_utc() -> datetime:
    return datetime.now(UTC)


def to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
