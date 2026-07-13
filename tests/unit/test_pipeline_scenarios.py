from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest

from news_intelligence.ingestion.adapters import coerce_raw_news_items
from news_intelligence.models import NewsAnalysisResult
from news_intelligence.pipeline import NewsIntelligencePipeline
from news_intelligence.storage import RepositoryBundle

FIXED_NOW = datetime(2026, 7, 11, 12, 0, tzinfo=UTC)
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "scenarios.json"


def load_scenarios() -> list[dict[str, Any]]:
    with FIXTURES.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    assert isinstance(payload, list)
    return [
        cast(dict[str, Any], scenario)
        for scenario in payload
        if isinstance(scenario, dict)
    ]


def expand_items(scenario: dict[str, Any]) -> list[dict[str, Any]]:
    items = cast(list[dict[str, Any]], scenario["items"])
    repeat = int(scenario.get("repeat", 1))
    if repeat == 1:
        return items
    expanded: list[dict[str, Any]] = []
    for index in range(repeat):
        item = deepcopy(items[0])
        item["source_article_id"] = f"{item['source_article_id']}-{index:02d}"
        item["published_at"] = f"2026-07-11T09:{14 + (index % 10):02d}:00Z"
        expanded.append(item)
    return expanded


@pytest.mark.parametrize("scenario", load_scenarios(), ids=lambda scenario: scenario["id"])
def test_required_news_scenarios(scenario: dict[str, Any]) -> None:
    db_path = _scenario_db_path(str(scenario["id"]))
    pipeline = NewsIntelligencePipeline(
        repositories=RepositoryBundle(db_path),
        clock=lambda: FIXED_NOW,
    )
    raw_items = coerce_raw_news_items(expand_items(scenario))
    result = pipeline.analyse(raw_items, persist=False)
    expected = scenario["expect"]

    assert any(event.event_type.value == expected["event_type"] for event in result.events)
    assert any(event.event_subtype == expected["event_subtype"] for event in result.events)
    if "event_direction" in expected:
        assert any(
            event.analysis.direction.value == expected["event_direction"]
            for event in result.events
        )

    signals = {signal.instrument.symbol: signal for signal in result.signals}
    for symbol, direction in expected.get("signals", {}).items():
        assert symbol in signals
        assert signals[symbol].signal.direction.value == direction

    for symbol in expected.get("can_veto", []):
        assert signals[symbol].decision.can_veto_trade is True

    if expected.get("contradictions"):
        assert any(event.contradictions_detected for event in result.events)
        assert any(cluster.contradictions_detected for cluster in result.clusters)

    if "cluster_article_count" in expected:
        assert any(
            cluster.article_count == expected["cluster_article_count"]
            for cluster in result.clusters
        )

    if "cluster_duplicate_count" in expected:
        assert any(
            cluster.duplicate_count == expected["cluster_duplicate_count"]
            for cluster in result.clusters
        )

    if "evidence_event_count" in expected:
        assert any(
            signal.evidence.event_count == expected["evidence_event_count"]
            for signal in result.signals
        )

    assert all(0.0 <= signal.signal.confidence <= 1.0 for signal in result.signals)
    assert all(-1.0 <= impact.directional_strength <= 1.0 for impact in result.impacts)


def test_persisted_duplicate_submission_increases_article_count() -> None:
    db_path = _scenario_db_path("persisted_duplicate_submission")
    pipeline = NewsIntelligencePipeline(
        repositories=RepositoryBundle(db_path),
        clock=lambda: FIXED_NOW,
    )
    scenario = next(
        item for item in load_scenarios() if item["id"] == "nvda_earnings_beat_raise"
    )
    raw_items = coerce_raw_news_items(expand_items(scenario))

    first_result = pipeline.analyse(raw_items, persist=True)
    second_result = pipeline.analyse(raw_items, persist=True)

    first_cluster = first_result.clusters[0]
    second_cluster = second_result.clusters[0]
    stored_cluster = pipeline.repositories.clusters.get(second_cluster.cluster_id)

    assert first_cluster.article_count == 1
    assert second_cluster.article_count == 2
    assert second_cluster.duplicate_count == 1
    assert second_result.signals[0].evidence.article_count == 2
    assert second_result.signals[0].evidence.duplicate_count == 1
    assert second_result.signals[0].evidence.event_count == 1
    assert stored_cluster is not None
    assert stored_cluster["article_count"] == 2
    assert stored_cluster["duplicate_count"] == 1


def test_three_step_takeover_material_update_versions_signal_snapshots() -> None:
    result = _analyse_fixture("three_step_takeover_material_update", persist=False)
    cluster = result.clusters[0]

    assert cluster.article_count == 3
    assert cluster.duplicate_count == 1
    assert cluster.update_count == 1
    assert cluster.canonical_event is not None
    assert cluster.canonical_event.event_status.value == "confirmed"
    assert len(cluster.signal_snapshots) == 2
    assert cluster.signal_snapshots[-1].confidence > cluster.signal_snapshots[0].confidence
    assert [article.classification.value for article in cluster.articles] == [
        "NEW_EVENT",
        "DUPLICATE",
        "MATERIAL_UPDATE",
    ]


def test_duplicate_never_increases_signal_strength() -> None:
    db_path = _scenario_db_path("duplicate_signal_strength")
    pipeline = NewsIntelligencePipeline(
        repositories=RepositoryBundle(db_path),
        clock=lambda: FIXED_NOW,
    )
    original, duplicate, _confirmation = _three_step_takeover_items()

    first = pipeline.analyse(coerce_raw_news_items(original), persist=True)
    second = pipeline.analyse(coerce_raw_news_items(duplicate), persist=True)
    first_signal = _signal_for(first, "AAPL")
    second_signal = _signal_for(second, "AAPL")

    assert second.clusters[0].article_count == 2
    assert second.clusters[0].duplicate_count == 1
    assert second.clusters[0].update_count == 0
    assert len(second.clusters[0].signal_snapshots) == 1
    assert second_signal.signal.directional_strength == first_signal.signal.directional_strength
    assert second_signal.signal.confidence == first_signal.signal.confidence
    assert second_signal.evidence.article_count == 2


def test_material_update_triggers_recalculation() -> None:
    db_path = _scenario_db_path("material_update_recalculation")
    pipeline = NewsIntelligencePipeline(
        repositories=RepositoryBundle(db_path),
        clock=lambda: FIXED_NOW,
    )
    original, _duplicate, confirmation = _three_step_takeover_items()

    first = pipeline.analyse(coerce_raw_news_items(original), persist=True)
    second = pipeline.analyse(coerce_raw_news_items(confirmation), persist=True)

    assert first.clusters[0].requires_recalculation is True
    assert second.clusters[0].requires_recalculation is True
    assert second.clusters[0].update_count == 1
    assert len(second.clusters[0].signal_snapshots) == 2
    assert _signal_for(second, "AAPL").signal.confidence > _signal_for(
        first,
        "AAPL",
    ).signal.confidence


def test_company_denial_reduces_active_signal() -> None:
    db_path = _scenario_db_path("denial_reduces_signal")
    pipeline = NewsIntelligencePipeline(
        repositories=RepositoryBundle(db_path),
        clock=lambda: FIXED_NOW,
    )
    original = _three_step_takeover_items()[0]
    denial = {
        "headline": "Apple denies takeover report and says no discussions are active",
        "body": "The company denial contradicted the earlier takeover report.",
        "source_name": "Company Press Release",
        "source_type": "company",
        "published_at": "2026-07-11T10:45:00Z",
        "known_ticker": "AAPL",
        "source_article_id": "aapl-denial-material-001",
    }

    first = pipeline.analyse(coerce_raw_news_items(original), persist=True)
    second = pipeline.analyse(coerce_raw_news_items(denial), persist=True)

    assert second.clusters[0].canonical_event is not None
    assert second.clusters[0].canonical_event.event_status.value == "denied"
    assert second.clusters[0].update_count == 1
    assert len(second.clusters[0].signal_snapshots) == 2
    assert _signal_for(second, "AAPL").signal.directional_strength < _signal_for(
        first,
        "AAPL",
    ).signal.directional_strength
    assert _signal_for(second, "AAPL").decision.can_veto_trade is True


def test_new_event_same_company_creates_separate_cluster() -> None:
    original = _three_step_takeover_items()[0]
    product = {
        "headline": "Apple announces anticipated product launch at developer event",
        "body": "The product update had been widely expected by analysts.",
        "source_name": "Company Press Release",
        "source_type": "company",
        "published_at": "2026-07-11T11:00:00Z",
        "known_ticker": "AAPL",
        "source_article_id": "aapl-product-new-cluster-001",
    }

    result = _analyse_items([original, product], persist=False)

    assert len(result.clusters) == 2
    assert {cluster.event_group for cluster in result.clusters} == {
        "merger_acquisition",
        "product",
    }


def test_missing_extracted_facts_do_not_create_material_update() -> None:
    result = _analyse_items(_three_step_takeover_items()[:2], persist=False)
    cluster = result.clusters[0]

    assert cluster.article_count == 2
    assert cluster.duplicate_count == 1
    assert cluster.update_count == 0
    assert len(cluster.signal_snapshots) == 1


def test_dashboard_exposes_update_counts_and_versions() -> None:
    root = Path(__file__).resolve().parents[2]
    renderers = (root / "frontend" / "js" / "renderers.js").read_text(encoding="utf-8")
    app = (root / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
    index = (root / "frontend" / "index.html").read_text(encoding="utf-8")

    assert "Update count" in renderers
    assert "Classification" in renderers
    assert "material_update" in renderers
    assert "event_versions" in app
    assert "signal_snapshots" in app
    assert "delete-current-test-run" in app
    assert "renderTestRuns" in renderers
    assert "options-sources" in app
    assert "event-list" in app
    assert "renderEventRows" in renderers
    assert "renderCompactImpacts" in renderers
    assert "poll-sec-edgar" in app
    assert "sec-edgar-poll-status" in app
    assert "renderSourceFilings" in renderers
    assert "options-storage" in app
    assert "storage-layers" in app
    assert "refreshStorage" in app
    assert "renderStorageLayers" in renderers
    assert "data-retention-layer" in renderers
    assert "dry-run-retention" in app
    assert "apply-retention-policy" in app
    assert "storageRetentionDryRun" in app
    assert "applyStorageRetention" in app
    assert "renderRetentionPlan" in renderers
    assert "run-automation-now" in app
    assert "automationRunNow" in app
    assert "renderAutomationRuns" in renderers
    assert "recent_runs" in renderers
    assert "backfill-symbols" in index
    assert "selectedBackfillSymbols" in app
    assert "renderBackfillSymbols" in app
    summary_views = re.search(r'class="summary-cards[^"]*" data-views="([^"]+)"', index)
    assert summary_views is not None
    assert "market-data" not in summary_views.group(1).split()


def test_takeover_fixture_isolated_across_test_runs(isolated_database: Path) -> None:
    pipeline = NewsIntelligencePipeline(
        repositories=RepositoryBundle(isolated_database),
        clock=lambda: FIXED_NOW,
    )

    first = pipeline.analyse(
        coerce_raw_news_items(
            {
                "test_run_id": "acceptance_run_one",
                "record_environment": "test",
                "items": _three_step_takeover_items(),
            }
        ),
        persist=True,
    )
    second = pipeline.analyse(
        coerce_raw_news_items(
            {
                "test_run_id": "acceptance_run_two",
                "record_environment": "test",
                "items": _three_step_takeover_items(),
            }
        ),
        persist=True,
    )

    assert _cluster_counts(first) == {
        "article_count": 3,
        "duplicate_count": 1,
        "update_count": 1,
    }
    assert _cluster_counts(second) == {
        "article_count": 3,
        "duplicate_count": 1,
        "update_count": 1,
    }
    assert _cluster_counts(second) != {
        "article_count": 6,
        "duplicate_count": 2,
        "update_count": 2,
    }


def test_delete_development_data_retains_production_records(isolated_database: Path) -> None:
    repositories = RepositoryBundle(isolated_database)
    pipeline = NewsIntelligencePipeline(
        repositories=repositories,
        clock=lambda: FIXED_NOW,
    )
    pipeline.analyse(
        coerce_raw_news_items(
            {
                "test_run_id": "delete_me",
                "record_environment": "test",
                "items": _three_step_takeover_items(),
            }
        ),
        persist=True,
    )
    repositories.events.save(
        "prod_evt_1",
        {
            "event_id": "prod_evt_1",
            "record_environment": "production",
            "test_run_id": None,
        },
    )

    deleted = repositories.delete_development_data()

    assert sum(deleted.values()) > 0
    assert repositories.events.get("prod_evt_1") is not None


def _analyse_fixture(fixture_id: str, *, persist: bool) -> NewsAnalysisResult:
    scenario = next(item for item in load_scenarios() if item["id"] == fixture_id)
    return _analyse_items(expand_items(scenario), persist=persist, scenario_id=fixture_id)


def _analyse_items(
    items: list[dict[str, Any]],
    *,
    persist: bool,
    scenario_id: str = "ad_hoc",
) -> NewsAnalysisResult:
    pipeline = NewsIntelligencePipeline(
        repositories=RepositoryBundle(_scenario_db_path(scenario_id)),
        clock=lambda: FIXED_NOW,
    )
    return pipeline.analyse(coerce_raw_news_items(items), persist=persist)


def _three_step_takeover_items() -> list[dict[str, Any]]:
    scenario = next(
        item for item in load_scenarios() if item["id"] == "three_step_takeover_material_update"
    )
    return expand_items(scenario)


def _signal_for(result: NewsAnalysisResult, symbol: str) -> Any:
    return next(signal for signal in result.signals if signal.instrument.symbol == symbol)


def _cluster_counts(result: NewsAnalysisResult) -> dict[str, int]:
    cluster = result.clusters[0]
    return {
        "article_count": cluster.article_count,
        "duplicate_count": cluster.duplicate_count,
        "update_count": cluster.update_count,
    }


def _scenario_db_path(scenario_id: str) -> Path:
    output_dir = Path(__file__).resolve().parents[2] / ".testdata"
    output_dir.mkdir(exist_ok=True)
    safe_id = re.sub(r"[^a-zA-Z0-9_.-]+", "-", scenario_id)
    db_path = output_dir / f"{safe_id}.sqlite3"
    if db_path.exists():
        db_path.unlink()
    return db_path
