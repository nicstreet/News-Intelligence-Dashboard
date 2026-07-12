from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from news_intelligence.models import NewsSource, RawNewsItem


def coerce_raw_news_items(payload: Any) -> list[RawNewsItem]:
    if isinstance(payload, RawNewsItem):
        return [payload]
    if isinstance(payload, list):
        return [_coerce_one(item) for item in payload]
    if isinstance(payload, dict) and isinstance(payload.get("items"), list):
        metadata = {
            key: payload[key]
            for key in ("test_run_id", "record_environment")
            if payload.get(key) is not None
        }
        return [_coerce_one({**item, **metadata}) for item in payload["items"]]
    if isinstance(payload, dict):
        return [_coerce_one(payload)]
    raise ValueError(
        "Payload must be a raw news item, a list of items, or an object with an items list."
    )


def _coerce_one(payload: Any) -> RawNewsItem:
    if isinstance(payload, RawNewsItem):
        return payload
    if not isinstance(payload, dict):
        raise ValueError("Each raw news item must be an object.")

    data = dict(payload)
    if "article_body" in data and "body" not in data:
        data["body"] = data.pop("article_body")
    if "published_timestamp" in data and "published_at" not in data:
        data["published_at"] = data.pop("published_timestamp")

    if "source" not in data:
        source_name = str(data.pop("source_name", "Unknown Source") or "Unknown Source")
        source_type = str(data.pop("source_type", "unknown") or "unknown")
        source_url = data.pop("source_url", None)
        data["source"] = NewsSource(
            source_name=source_name,
            source_type=source_type,
            source_url=source_url,
        )

    if "known_ticker" in data and data.get("known_ticker") and "tickers" not in data:
        data["tickers"] = [str(data["known_ticker"]).upper()]

    try:
        return RawNewsItem.model_validate(data)
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc
