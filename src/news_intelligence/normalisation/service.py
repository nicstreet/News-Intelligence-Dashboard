from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime

from news_intelligence.config import NewsIntelligenceConfig
from news_intelligence.models import NewsSource, NormalisedNewsItem, RawNewsItem
from news_intelligence.utils import normalise_text, normalise_whitespace, stable_hash, to_utc


class NewsNormaliser:
    version = "normaliser-1.0.0"

    def __init__(
        self,
        config: NewsIntelligenceConfig,
        clock: Callable[[], datetime],
    ) -> None:
        self._config = config
        self._clock = clock

    def normalise(self, raw_item: RawNewsItem) -> NormalisedNewsItem:
        headline = normalise_whitespace(raw_item.headline)
        body = normalise_whitespace(raw_item.body or "")
        joined_text = normalise_text(f"{headline} {body}")
        content_hash = stable_hash(joined_text, prefix="sha256-", length=64)
        raw_id = raw_item.raw_id or stable_hash(
            headline,
            body,
            raw_item.source.source_name,
            raw_item.source_article_id,
            raw_item.published_at.isoformat(),
            raw_item.record_environment.value,
            raw_item.test_run_id,
            prefix="raw_",
        )
        source = self._resolve_source(raw_item.source)
        detected_symbols = self._detect_symbols(raw_item, joined_text)
        first_seen_at = raw_item.first_seen_at or self._clock()
        return NormalisedNewsItem(
            raw_id=raw_id,
            normalised_id=stable_hash(raw_id, content_hash, prefix="norm_"),
            headline=headline,
            body=body,
            normalised_text=joined_text,
            source=source,
            published_at=to_utc(raw_item.published_at),
            first_seen_at=to_utc(first_seen_at),
            content_hash=content_hash,
            source_article_id=raw_item.source_article_id,
            detected_symbols=detected_symbols,
            country=raw_item.country,
            market=raw_item.market,
            test_run_id=raw_item.test_run_id,
            record_environment=raw_item.record_environment,
            metadata=dict(raw_item.metadata),
        )

    def _resolve_source(self, source: NewsSource) -> NewsSource:
        profile = self._config.source_profile(source.source_name)
        default = float(self._config.source_credibility.get("default_credibility", 0.5))
        source_type = source.source_type
        if source_type == "unknown" and profile.get("source_type"):
            source_type = str(profile["source_type"])
        credibility = float(profile.get("credibility", source.source_credibility or default))
        return source.model_copy(
            update={
                "source_type": source_type,
                "source_credibility": max(0.0, min(1.0, credibility)),
            }
        )

    def _detect_symbols(self, raw_item: RawNewsItem, text: str) -> list[str]:
        known_symbols = self._config.known_symbols()
        candidates = {symbol.upper() for symbol in raw_item.tickers}
        if raw_item.known_ticker:
            candidates.add(raw_item.known_ticker.upper())

        for token in re.findall(r"\b[A-Z]{1,5}\b", f"{raw_item.headline} {raw_item.body or ''}"):
            if token in known_symbols:
                candidates.add(token)

        instruments = self._config.instrument_relationships.get("instruments", {})
        if isinstance(instruments, dict):
            for symbol, profile in instruments.items():
                if not isinstance(profile, dict):
                    continue
                aliases = [
                    str(profile.get("name", "")),
                    *[str(alias) for alias in profile.get("aliases", [])],
                ]
                if any(alias and normalise_text(alias) in text for alias in aliases):
                    candidates.add(str(symbol).upper())

        return sorted(symbol for symbol in candidates if symbol)
