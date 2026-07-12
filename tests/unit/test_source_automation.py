from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from news_intelligence.config import NewsIntelligenceConfig, load_config
from news_intelligence.pipeline import NewsIntelligencePipeline
from news_intelligence.sources.scheduler import SourceScheduler
from news_intelligence.storage import RepositoryBundle

FIXED_NOW = datetime(2026, 7, 12, 12, 0, tzinfo=UTC)


def test_automation_run_polls_due_world_source_and_records_run(
    isolated_database: Path,
) -> None:
    pipeline = NewsIntelligencePipeline(
        config=_automation_config(sec_enabled=False, world_enabled=True),
        repositories=RepositoryBundle(isolated_database),
        clock=lambda: FIXED_NOW,
    )

    run = SourceScheduler(pipeline).run_once(reason="unit_test")
    status = SourceScheduler(pipeline).status()

    assert run["reason"] == "unit_test"
    assert run["source_run_count"] == 1
    assert run["ingested_count"] == 2
    assert run["error_count"] == 0
    assert pipeline.repositories.automation_runs.get(str(run["automation_run_id"])) is not None
    assert status["recent_runs"][0]["automation_run_id"] == run["automation_run_id"]
    assert status["sources"][0]["connector_type"] in {"sec_edgar", "world_news"}


def test_automation_run_can_apply_retention_housekeeping(
    isolated_database: Path,
) -> None:
    repositories = RepositoryBundle(isolated_database)
    repositories.raw_news.save(
        "old_dev",
        {
            "raw_id": "old_dev",
            "headline": "Old development item",
            "published_at": "2026-05-01T09:00:00Z",
            "record_environment": "development",
        },
    )
    pipeline = NewsIntelligencePipeline(
        config=_automation_config(
            sec_enabled=False,
            world_enabled=False,
            retention_enabled=True,
            retention_days={"raw_news": 30},
        ),
        repositories=repositories,
        clock=lambda: FIXED_NOW,
    )

    run = SourceScheduler(pipeline).run_once(reason="retention_test")
    status = SourceScheduler(pipeline).status()

    assert run["retention_applied"] is True
    assert run["retention_result"]["total_deleted_records"] == 1
    assert repositories.raw_news.get("old_dev") is None
    assert status["retention"]["enabled"] is True
    assert status["recent_runs"][0]["retention_applied"] is True


def _automation_config(
    *,
    sec_enabled: bool,
    world_enabled: bool,
    retention_enabled: bool = False,
    retention_days: dict[str, Any] | None = None,
) -> NewsIntelligenceConfig:
    base = load_config()
    return replace(
        base,
        sec_edgar={**base.sec_edgar, "enabled": sec_enabled},
        world_news={**base.world_news, "enabled": world_enabled},
        automation={
            **base.automation,
            "enabled": True,
            "poll_due_on_startup": False,
            "scheduler_interval_seconds": 10,
            "retention": {
                "enabled": retention_enabled,
                "apply_on_startup": False,
                "interval_minutes": 1440,
                "retention_days": retention_days or {},
            },
        },
    )
