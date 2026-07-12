from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from news_intelligence.models import SourceConnectorStatus, SourceIngestionRun
from news_intelligence.pipeline import NewsIntelligencePipeline
from news_intelligence.sources.sec_edgar import SecEdgarConnector
from news_intelligence.sources.service import SourceIngestionService
from news_intelligence.sources.world_news import WorldNewsConnector


class SourceScheduler:
    def __init__(self, pipeline: NewsIntelligencePipeline) -> None:
        self._pipeline = pipeline
        self._service = SourceIngestionService(pipeline)

    def status(self) -> dict[str, Any]:
        statuses = [self._status_payload(status) for status in self._statuses()]
        return {
            "enabled": bool(self._pipeline.config.automation.get("enabled", False)),
            "generated_at": self._pipeline.clock().isoformat(),
            "sources": statuses,
            "stale_count": sum(1 for status in statuses if status["stale"]),
            "due_count": sum(1 for status in statuses if status["due"]),
        }

    def poll_due(self, *, force: bool = False) -> list[SourceIngestionRun]:
        runs: list[SourceIngestionRun] = []
        for adapter in self._adapters():
            status = self._service.status_for(adapter)
            if force or self._is_due(status, self._pipeline.clock()):
                runs.append(self._service.ingest(adapter, force=force))
        return runs

    def _adapters(self) -> list[Any]:
        return [
            SecEdgarConnector(self._pipeline.config, clock=self._pipeline.clock),
            WorldNewsConnector(self._pipeline.config),
        ]

    def _statuses(self) -> list[SourceConnectorStatus]:
        return [self._service.status_for(adapter) for adapter in self._adapters()]

    def _status_payload(self, status: SourceConnectorStatus) -> dict[str, Any]:
        now = self._pipeline.clock()
        return {
            **status.model_dump(mode="json"),
            "due": self._is_due(status, now),
            "stale": self._is_stale(status, now),
        }

    def _is_due(self, status: SourceConnectorStatus, now: datetime) -> bool:
        if not status.enabled:
            return False
        if status.next_poll_after is None:
            return True
        return now >= status.next_poll_after

    def _is_stale(self, status: SourceConnectorStatus, now: datetime) -> bool:
        if not status.enabled:
            return False
        if status.last_polled_at is None:
            return True
        stale_after = self._stale_after(status.connector_type)
        return now - status.last_polled_at > stale_after

    def _stale_after(self, connector_type: str) -> timedelta:
        sources = self._pipeline.config.automation.get("sources", {})
        if not isinstance(sources, dict):
            return timedelta(hours=2)
        settings = sources.get(connector_type, {})
        if not isinstance(settings, dict):
            return timedelta(hours=2)
        return timedelta(minutes=int(settings.get("stale_after_minutes", 120)))
