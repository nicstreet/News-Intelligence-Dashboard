from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from news_intelligence.models import (
    RuntimeEnvironment,
    SourceConnectorStatus,
    SourceIngestionRun,
)
from news_intelligence.pipeline import NewsIntelligencePipeline
from news_intelligence.sources.eodhd_news import EodhdNewsConnector
from news_intelligence.sources.official_feeds import configured_official_feed_connectors
from news_intelligence.sources.sec_edgar import SecEdgarConnector
from news_intelligence.sources.service import SourceIngestionService
from news_intelligence.sources.world_news import WorldNewsConnector
from news_intelligence.storage.retention import StorageLayerSummaryService


class SourceScheduler:
    def __init__(self, pipeline: NewsIntelligencePipeline) -> None:
        self._pipeline = pipeline
        self._service = SourceIngestionService(pipeline)

    def status(self) -> dict[str, Any]:
        statuses = [self._status_payload(status) for status in self._statuses()]
        recent_runs = self.recent_runs(limit=10)
        return {
            "enabled": bool(self._pipeline.config.automation.get("enabled", False)),
            "poll_due_on_startup": bool(
                self._pipeline.config.automation.get("poll_due_on_startup", False)
            ),
            "scheduler_interval_seconds": self.interval_seconds(),
            "retention": self._retention_status(),
            "generated_at": self._pipeline.clock().isoformat(),
            "sources": statuses,
            "stale_count": sum(1 for status in statuses if status["stale"]),
            "due_count": sum(1 for status in statuses if status["due"]),
            "recent_runs": recent_runs,
            "last_run": recent_runs[0] if recent_runs else None,
        }

    def interval_seconds(self) -> int:
        return max(10, int(self._pipeline.config.automation.get("scheduler_interval_seconds", 60)))

    def poll_due(self, *, force: bool = False) -> list[SourceIngestionRun]:
        runs: list[SourceIngestionRun] = []
        for adapter in self._adapters():
            status = self._service.status_for(adapter)
            if not status.enabled:
                continue
            if force or self._is_due(status, self._pipeline.clock()):
                runs.append(self._ingest_with_retries(adapter, force=force))
        return runs

    def run_once(
        self,
        *,
        force_sources: bool = False,
        apply_retention: bool | None = None,
        reason: str = "manual",
    ) -> dict[str, Any]:
        started_at = self._pipeline.clock()
        errors: list[str] = []
        source_runs: list[SourceIngestionRun] = []
        retention_result: dict[str, Any] | None = None

        try:
            source_runs = self.poll_due(force=force_sources)
        except Exception as exc:
            errors.append(str(exc))

        should_apply_retention = (
            self._retention_due(started_at)
            if apply_retention is None
            else apply_retention
        )
        if should_apply_retention:
            try:
                retention_result = StorageLayerSummaryService(
                    self._pipeline.config,
                    self._pipeline.repositories,
                    clock=self._pipeline.clock,
                ).apply_retention(self._retention_days())
            except Exception as exc:
                errors.append(str(exc))

        completed_at = self._pipeline.clock()
        payload = {
            "automation_run_id": f"auto_{uuid4().hex[:12]}",
            "reason": reason,
            "record_environment": self._runtime_environment().value,
            "started_at": started_at.isoformat(),
            "completed_at": completed_at.isoformat(),
            "source_run_count": len(source_runs),
            "fetched_count": sum(run.fetched_count for run in source_runs),
            "ingested_count": sum(run.ingested_count for run in source_runs),
            "skipped_count": sum(run.skipped_count for run in source_runs),
            "error_count": sum(run.error_count for run in source_runs) + len(errors),
            "errors": [*errors, *[error for run in source_runs for error in run.errors]],
            "source_runs": [self._run_payload(run) for run in source_runs],
            "retention_applied": retention_result is not None,
            "retention_result": retention_result,
        }
        self._pipeline.repositories.automation_runs.save(
            str(payload["automation_run_id"]),
            payload,
        )
        return payload

    def recent_runs(self, *, limit: int = 20) -> list[dict[str, Any]]:
        return self._pipeline.repositories.automation_runs.list_recent(limit)

    def _adapters(self) -> list[Any]:
        return [
            SecEdgarConnector(self._pipeline.config, clock=self._pipeline.clock),
            WorldNewsConnector(self._pipeline.config),
            EodhdNewsConnector(self._pipeline.config, clock=self._pipeline.clock),
            *configured_official_feed_connectors(
                self._pipeline.config,
                clock=self._pipeline.clock,
            ),
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

    def _run_payload(self, run: SourceIngestionRun) -> dict[str, Any]:
        return {
            "source_name": run.source_name,
            "connector_type": run.connector_type,
            "started_at": run.started_at.isoformat(),
            "completed_at": run.completed_at.isoformat(),
            "fetched_count": run.fetched_count,
            "ingested_count": run.ingested_count,
            "skipped_count": run.skipped_count,
            "error_count": run.error_count,
            "errors": run.errors,
            "status": run.status.model_dump(mode="json"),
        }

    def _ingest_with_retries(self, adapter: Any, *, force: bool) -> SourceIngestionRun:
        max_attempts = self._retry_attempts(str(adapter.connector_type)) + 1
        last_run: SourceIngestionRun | None = None
        for _attempt in range(max_attempts):
            last_run = self._service.ingest(adapter, force=force)
            if last_run.error_count == 0:
                return last_run
        if last_run is None:
            raise RuntimeError(f"No ingestion run produced for {adapter.connector_type}")
        return last_run

    def _retention_status(self) -> dict[str, Any]:
        settings = self._retention_settings()
        return {
            "enabled": bool(settings.get("enabled", False)),
            "apply_on_startup": bool(settings.get("apply_on_startup", False)),
            "interval_minutes": int(settings.get("interval_minutes", 1440)),
            "due": self._retention_due(self._pipeline.clock()),
        }

    def _retention_due(self, now: datetime) -> bool:
        settings = self._retention_settings()
        if not bool(settings.get("enabled", False)):
            return False
        last_retention_at = self._last_retention_at()
        if last_retention_at is None:
            return True
        interval = timedelta(minutes=int(settings.get("interval_minutes", 1440)))
        return now - last_retention_at >= interval

    def _last_retention_at(self) -> datetime | None:
        for run in self.recent_runs(limit=100):
            if not run.get("retention_applied"):
                continue
            completed_at = run.get("completed_at")
            if not isinstance(completed_at, str):
                continue
            try:
                return datetime.fromisoformat(completed_at)
            except ValueError:
                continue
        return None

    def _retention_settings(self) -> dict[str, Any]:
        settings = self._pipeline.config.automation.get("retention", {})
        return settings if isinstance(settings, dict) else {}

    def _retention_days(self) -> dict[str, Any]:
        days = self._retention_settings().get("retention_days", {})
        return days if isinstance(days, dict) else {}

    def _runtime_environment(self) -> RuntimeEnvironment:
        try:
            return RuntimeEnvironment(self._pipeline.config.environment)
        except ValueError:
            return RuntimeEnvironment.DEVELOPMENT

    def _stale_after(self, connector_type: str) -> timedelta:
        sources = self._pipeline.config.automation.get("sources", {})
        if not isinstance(sources, dict):
            return timedelta(hours=2)
        settings = sources.get(connector_type, {})
        if not isinstance(settings, dict):
            return timedelta(hours=2)
        return timedelta(minutes=int(settings.get("stale_after_minutes", 120)))

    def _retry_attempts(self, connector_type: str) -> int:
        sources = self._pipeline.config.automation.get("sources", {})
        if not isinstance(sources, dict):
            return 0
        settings = sources.get(connector_type, {})
        if not isinstance(settings, dict):
            return 0
        return max(0, int(settings.get("retry_attempts", 0)))
