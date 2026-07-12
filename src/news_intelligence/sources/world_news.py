from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta
from typing import Any

from news_intelligence.config import NewsIntelligenceConfig
from news_intelligence.models import (
    NewsSource,
    RawNewsItem,
    RuntimeEnvironment,
    SourceIngestedItem,
)
from news_intelligence.utils import now_utc


class WorldNewsConnector:
    adapter_id = "world_news_json"

    def __init__(self, config: NewsIntelligenceConfig) -> None:
        self._config = config
        self._settings = config.world_news
        self.source_name = str(self._settings.get("source_name", "World News Monitor"))
        self.connector_type = str(self._settings.get("connector_type", "world_news"))
        self.enabled = bool(self._settings.get("enabled", True))
        self.poll_interval = timedelta(
            seconds=int(self._settings.get("poll_interval_seconds", 900))
        )
        self.country_or_region = str(self._settings.get("country_or_region", "global"))
        self.source_class = str(self._settings.get("source_class", "geopolitical_macro"))

    def fetch(
        self,
        known_source_record_ids: set[str] | None = None,
    ) -> Sequence[SourceIngestedItem]:
        if not self.enabled:
            return []
        known = known_source_record_ids or set()
        records: list[SourceIngestedItem] = []
        items = self._settings.get("items", [])
        if not isinstance(items, list):
            return []
        for item in items:
            if not isinstance(item, dict):
                continue
            source_record_id = str(item.get("source_record_id", ""))
            if not source_record_id or source_record_id in known:
                continue
            records.append(self._record_from_config(item, source_record_id))
        return records

    def to_raw_news_item(self, item: SourceIngestedItem) -> RawNewsItem:
        metadata = dict(item.metadata)
        return RawNewsItem(
            headline=item.headline,
            body=str(metadata.pop("body", "")),
            source=NewsSource(
                source_name=item.source_name,
                source_type=str(self._settings.get("source_type", "newswire")),
                source_url=item.source_url,
            ),
            published_at=item.published_at,
            first_seen_at=item.ingested_at,
            source_article_id=item.source_record_id,
            tickers=self._strings(metadata.pop("tickers", []), upper=True),
            country=str(metadata.pop("country", "")) or None,
            market=str(metadata.pop("market", "")) or None,
            record_environment=self._runtime_environment(),
            metadata={
                **metadata,
                "connector_type": self.connector_type,
                "world_news": True,
            },
        )

    def _record_from_config(
        self,
        item: dict[str, Any],
        source_record_id: str,
    ) -> SourceIngestedItem:
        metadata = dict(item.get("metadata", {})) if isinstance(item.get("metadata"), dict) else {}
        metadata.update(
            {
                "body": item.get("body", ""),
                "country": item.get("country"),
                "market": item.get("market"),
                "tickers": item.get("tickers", []),
            }
        )
        return SourceIngestedItem(
            source_record_id=source_record_id,
            source_name=self.source_name,
            connector_type=self.connector_type,
            headline=str(item.get("headline", "World news item")),
            published_at=item.get("published_at") or now_utc(),
            source_url=str(item.get("source_url", "")) or None,
            ingested_at=now_utc(),
            metadata=metadata,
            record_environment=self._runtime_environment(),
        )

    def _strings(self, value: object, *, upper: bool = False) -> list[str]:
        if not isinstance(value, list):
            return []
        items = [str(item) for item in value if item]
        return [item.upper() for item in items] if upper else items

    def _runtime_environment(self) -> RuntimeEnvironment:
        try:
            return RuntimeEnvironment(self._config.environment)
        except ValueError:
            return RuntimeEnvironment.DEVELOPMENT
