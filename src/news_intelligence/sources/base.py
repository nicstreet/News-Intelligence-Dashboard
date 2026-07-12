from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta
from typing import Protocol

from news_intelligence.models import RawNewsItem, SourceIngestedItem

SourceRecord = SourceIngestedItem


class SourceAdapter(Protocol):
    adapter_id: str
    source_name: str
    connector_type: str
    enabled: bool
    poll_interval: timedelta

    def fetch(
        self,
        known_source_record_ids: set[str] | None = None,
    ) -> Sequence[SourceRecord]:
        """Fetch source records that are candidates for ingestion."""

    def to_raw_news_item(self, filing: SourceRecord) -> RawNewsItem:
        """Convert a source record into the pipeline's raw news contract."""
