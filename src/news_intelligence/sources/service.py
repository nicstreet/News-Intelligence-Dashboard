from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Any

from news_intelligence.models import (
    RuntimeEnvironment,
    SourceConnectorState,
    SourceConnectorStatus,
    SourceIngestedFiling,
    SourceIngestionRun,
)
from news_intelligence.pipeline import NewsIntelligencePipeline
from news_intelligence.sources.base import SourceAdapter, SourceRecord

ProgressCallback = Callable[[dict[str, Any]], None]


class SourceIngestionService:
    def __init__(self, pipeline: NewsIntelligencePipeline) -> None:
        self._pipeline = pipeline
        self._repositories = pipeline.repositories

    def ingest(
        self,
        adapter: SourceAdapter,
        *,
        force: bool = False,
        progress: ProgressCallback | None = None,
        connector_index: int = 1,
        connector_total: int = 1,
    ) -> SourceIngestionRun:
        started_at = self._pipeline.clock()
        previous_status = self._stored_status(adapter.adapter_id)
        if not force and previous_status is not None and previous_status.last_polled_at is not None:
            next_poll_after = previous_status.last_polled_at + adapter.poll_interval
            if started_at < next_poll_after:
                status = previous_status.model_copy(update={"next_poll_after": next_poll_after})
                return SourceIngestionRun(
                    source_name=adapter.source_name,
                    connector_type=adapter.connector_type,
                    started_at=started_at,
                    completed_at=self._pipeline.clock(),
                    fetched_count=0,
                    ingested_count=0,
                    skipped_count=0,
                    error_count=0,
                    items=[],
                    filings=[],
                    status=status,
                )

        known_ids = self._known_source_record_ids(adapter.connector_type)
        errors: list[str] = []
        fetched_items: list[SourceRecord] = []
        self._progress(
            progress,
            adapter=adapter,
            connector_index=connector_index,
            connector_total=connector_total,
            phase="fetching_source",
            message=f"Fetching {adapter.source_name}",
        )
        try:
            fetched_items = list(adapter.fetch(known_ids))
        except Exception as exc:
            errors.append(str(exc))
        return self._ingest_fetched(
            adapter=adapter,
            previous_status=previous_status,
            started_at=started_at,
            fetched_items=fetched_items,
            fetch_errors=errors,
            progress=progress,
            connector_index=connector_index,
            connector_total=connector_total,
        )

    def ingest_fetched(
        self,
        adapter: SourceAdapter,
        fetched_items: Sequence[SourceRecord],
        *,
        progress: ProgressCallback | None = None,
        connector_index: int = 1,
        connector_total: int = 1,
    ) -> SourceIngestionRun:
        return self._ingest_fetched(
            adapter=adapter,
            previous_status=self._stored_status(adapter.adapter_id),
            started_at=self._pipeline.clock(),
            fetched_items=list(fetched_items),
            fetch_errors=[],
            progress=progress,
            connector_index=connector_index,
            connector_total=connector_total,
        )

    def known_source_record_ids(self, connector_type: str) -> set[str]:
        return self._known_source_record_ids(connector_type)

    def _ingest_fetched(
        self,
        *,
        adapter: SourceAdapter,
        previous_status: SourceConnectorStatus | None,
        started_at: datetime,
        fetched_items: list[SourceRecord],
        fetch_errors: list[str],
        progress: ProgressCallback | None,
        connector_index: int,
        connector_total: int,
    ) -> SourceIngestionRun:
        errors: list[str] = []
        ingested_items: list[SourceRecord] = []
        skipped_count = 0
        errors.extend(fetch_errors)
        record_total = len(fetched_items)
        self._progress(
            progress,
            adapter=adapter,
            connector_index=connector_index,
            connector_total=connector_total,
            record_total=record_total,
            phase="processing_records",
            message=f"Processing {adapter.source_name}",
        )
        try:
            for record_index, source_item in enumerate(fetched_items, start=1):
                self._progress(
                    progress,
                    adapter=adapter,
                    connector_index=connector_index,
                    connector_total=connector_total,
                    record_index=record_index,
                    record_total=record_total,
                    fetched_count=record_total,
                    ingested_count=len(ingested_items),
                    skipped_count=skipped_count,
                    phase="processing_records",
                    message=source_item.headline,
                )
                if self._repositories.source_filings.get(source_item.source_record_id) is not None:
                    skipped_count += 1
                    continue
                raw_item = adapter.to_raw_news_item(source_item)
                result = self._pipeline.analyse([raw_item], persist=True)
                event = result.events[0] if result.events else None
                cluster = result.clusters[0] if result.clusters else None
                stored_item = source_item.model_copy(
                    update={
                        "raw_id": (
                            result.raw_items[0].raw_id
                            if result.raw_items
                            else raw_item.raw_id
                        ),
                        "event_id": event.event_id if event else None,
                        "cluster_id": cluster.cluster_id if cluster else None,
                        "record_environment": self._runtime_environment(),
                        "metadata": {
                            **source_item.metadata,
                            "analysis_request_id": result.request_id,
                        },
                    }
                )
                self._repositories.source_filings.save(
                    stored_item.source_record_id,
                    stored_item,
                )
                ingested_items.append(stored_item)
        except Exception as exc:
            errors.append(str(exc))
        self._progress(
            progress,
            adapter=adapter,
            connector_index=connector_index,
            connector_total=connector_total,
            record_index=record_total,
            record_total=record_total,
            fetched_count=record_total,
            ingested_count=len(ingested_items),
            skipped_count=skipped_count,
            error_count=len(errors),
            phase="source_complete",
            message=f"Completed {adapter.source_name}",
        )

        completed_at = self._pipeline.clock()
        status = self._status(
            adapter=adapter,
            previous_status=previous_status,
            completed_at=completed_at,
            ingested_count=len(ingested_items),
            errors=errors,
        )
        self._repositories.source_status.save(adapter.adapter_id, status)
        ingested_filings = [
            item for item in ingested_items if isinstance(item, SourceIngestedFiling)
        ]
        return SourceIngestionRun(
            source_name=adapter.source_name,
            connector_type=adapter.connector_type,
            started_at=started_at,
            completed_at=completed_at,
            fetched_count=len(fetched_items),
            ingested_count=len(ingested_items),
            skipped_count=skipped_count,
            error_count=len(errors),
            errors=errors,
            items=ingested_items,
            filings=ingested_filings,
            status=status,
        )

    def status_for(self, adapter: SourceAdapter) -> SourceConnectorStatus:
        stored = self._stored_status(adapter.adapter_id)
        if stored is not None:
            return stored
        return SourceConnectorStatus(
            source_name=adapter.source_name,
            country_or_region=str(getattr(adapter, "country_or_region", "unknown")),
            source_class=str(getattr(adapter, "source_class", "unknown")),
            connector_type=adapter.connector_type,
            enabled=adapter.enabled,
            current_status=(
                SourceConnectorState.OK if adapter.enabled else SourceConnectorState.DISABLED
            ),
            items_ingested=self._items_ingested(adapter.connector_type),
        )

    def recent_filings(self, limit: int = 50) -> list[dict[str, object]]:
        return self._repositories.source_filings.list_recent(limit)

    def _known_source_record_ids(self, connector_type: str) -> set[str]:
        return {
            str(record["source_record_id"])
            for record in self._repositories.source_filings.list_all()
            if record.get("connector_type") == connector_type and record.get("source_record_id")
        }

    def _stored_status(self, adapter_id: str) -> SourceConnectorStatus | None:
        payload = self._repositories.source_status.get(adapter_id)
        return SourceConnectorStatus.model_validate(payload) if payload else None

    def _status(
        self,
        *,
        adapter: SourceAdapter,
        previous_status: SourceConnectorStatus | None,
        completed_at: datetime,
        ingested_count: int,
        errors: list[str],
    ) -> SourceConnectorStatus:
        previous_items = previous_status.items_ingested if previous_status is not None else 0
        return SourceConnectorStatus(
            source_name=adapter.source_name,
            country_or_region=str(getattr(adapter, "country_or_region", "unknown")),
            source_class=str(getattr(adapter, "source_class", "unknown")),
            connector_type=adapter.connector_type,
            enabled=adapter.enabled,
            current_status=SourceConnectorState.ERROR if errors else SourceConnectorState.OK,
            last_successful_ingestion=(
                completed_at
                if ingested_count > 0
                or (previous_status and previous_status.last_successful_ingestion)
                else None
            ),
            last_failure=errors[-1] if errors else None,
            last_polled_at=completed_at,
            next_poll_after=completed_at + adapter.poll_interval,
            items_ingested=previous_items + ingested_count,
        )

    def _items_ingested(self, connector_type: str) -> int:
        return sum(
            1
            for record in self._repositories.source_filings.list_all()
            if record.get("connector_type") == connector_type
        )

    def _runtime_environment(self) -> RuntimeEnvironment:
        try:
            return RuntimeEnvironment(self._pipeline.config.environment)
        except ValueError:
            return RuntimeEnvironment.DEVELOPMENT

    def _progress(
        self,
        progress: ProgressCallback | None,
        *,
        adapter: SourceAdapter,
        connector_index: int,
        connector_total: int,
        **updates: Any,
    ) -> None:
        if progress is None:
            return
        progress(
            {
                "connector_name": adapter.source_name,
                "connector_type": adapter.connector_type,
                "connector_index": connector_index,
                "connector_total": connector_total,
                **updates,
            }
        )
