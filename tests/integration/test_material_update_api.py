from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from news_intelligence.api import routes
from news_intelligence.main import create_app
from news_intelligence.pipeline import NewsIntelligencePipeline
from news_intelligence.storage import RepositoryBundle

FIXED_NOW = datetime(2026, 7, 11, 12, 0, tzinfo=UTC)


def test_api_material_update_preserves_duplicate_and_versions() -> None:
    db_path = _scenario_db_path("api_material_update")
    routes.pipeline = NewsIntelligencePipeline(
        repositories=RepositoryBundle(db_path),
        clock=lambda: FIXED_NOW,
    )
    client = TestClient(create_app())
    original, duplicate, confirmation = _three_step_takeover_items()

    first = client.post("/news/analyse", json=original)
    second = client.post("/news/analyse", json=duplicate)
    third = client.post("/news/analyse", json=confirmation)

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 200
    first_payload = first.json()
    second_payload = second.json()
    third_payload = third.json()

    assert first_payload["clusters"][0]["article_count"] == 1
    assert first_payload["clusters"][0]["update_count"] == 0
    assert second_payload["clusters"][0]["article_count"] == 2
    assert second_payload["clusters"][0]["duplicate_count"] == 1
    assert second_payload["clusters"][0]["update_count"] == 0
    assert third_payload["clusters"][0]["article_count"] == 3
    assert third_payload["clusters"][0]["duplicate_count"] == 1
    assert third_payload["clusters"][0]["update_count"] == 1
    assert third_payload["clusters"][0]["canonical_event"]["event_status"] == "confirmed"
    assert len(third_payload["clusters"][0]["signal_snapshots"]) == 2
    assert (
        third_payload["clusters"][0]["signal_snapshots"][-1]["confidence"]
        > third_payload["clusters"][0]["signal_snapshots"][0]["confidence"]
    )


def test_api_test_run_controls_isolate_fixture_runs_and_reset_development_data() -> None:
    db_path = _scenario_db_path("api_test_run_controls")
    routes.pipeline = NewsIntelligencePipeline(
        repositories=RepositoryBundle(db_path),
        clock=lambda: FIXED_NOW,
    )
    client = TestClient(create_app())

    first_run = client.post("/test-runs")
    second_run = client.post("/test-runs")

    assert first_run.status_code == 200
    assert second_run.status_code == 200
    first_run_id = str(first_run.json()["test_run_id"])
    second_run_id = str(second_run.json()["test_run_id"])
    assert first_run_id != second_run_id

    first_result = client.post(
        "/news/analyse",
        json={
            "test_run_id": first_run_id,
            "record_environment": "test",
            "items": _three_step_takeover_items(),
        },
    )
    second_result = client.post(
        "/news/analyse",
        json={
            "test_run_id": second_run_id,
            "record_environment": "test",
            "items": _three_step_takeover_items(),
        },
    )

    assert first_result.status_code == 200
    assert second_result.status_code == 200
    assert _cluster_counts(first_result.json()) == {
        "article_count": 3,
        "duplicate_count": 1,
        "update_count": 1,
    }
    assert _cluster_counts(second_result.json()) == {
        "article_count": 3,
        "duplicate_count": 1,
        "update_count": 1,
    }
    assert _cluster_counts(second_result.json()) != {
        "article_count": 6,
        "duplicate_count": 2,
        "update_count": 2,
    }
    assert second_result.json()["clusters"][0]["test_run_id"] == second_run_id
    assert second_result.json()["signals"][0]["test_run_id"] == second_run_id

    historical_runs = client.get("/test-runs")
    assert historical_runs.status_code == 200
    historical_run_ids = {run["test_run_id"] for run in historical_runs.json()}
    assert {first_run_id, second_run_id}.issubset(historical_run_ids)

    delete_first = client.delete(f"/test-runs/{first_run_id}")
    assert delete_first.status_code == 200
    assert delete_first.json()["deleted"]["event_clusters"] == 1

    routes.pipeline.repositories.events.save(
        "prod_evt_api_1",
        {
            "event_id": "prod_evt_api_1",
            "record_environment": "production",
            "test_run_id": None,
        },
    )
    reset = client.delete("/development-data")

    assert reset.status_code == 200
    assert routes.pipeline.repositories.events.get("prod_evt_api_1") is not None


def _three_step_takeover_items() -> list[dict[str, Any]]:
    return [
        {
            "headline": "Apple may receive a takeover approach according to report",
            "body": "A report says Apple may receive a takeover approach.",
            "source_name": "Market Blog",
            "source_type": "blog",
            "published_at": "2026-07-11T10:00:00Z",
            "known_ticker": "AAPL",
            "source_article_id": "api-three-step-001",
        },
        {
            "headline": (
                "Another publisher repeats the Apple takeover report without adding evidence"
            ),
            "body": "The takeover report repeats the prior claim without additional evidence.",
            "source_name": "Example Newswire",
            "source_type": "newswire",
            "published_at": "2026-07-11T10:10:00Z",
            "known_ticker": "AAPL",
            "source_article_id": "api-three-step-002",
        },
        {
            "headline": "Apple confirms that it has received a preliminary takeover approach",
            "body": "Company confirms that it has received a preliminary takeover approach.",
            "source_name": "Company Press Release",
            "source_type": "company",
            "published_at": "2026-07-11T10:30:00Z",
            "known_ticker": "AAPL",
            "source_article_id": "api-three-step-003",
        },
    ]


def _cluster_counts(payload: dict[str, Any]) -> dict[str, int]:
    cluster = payload["clusters"][0]
    return {
        "article_count": int(cluster["article_count"]),
        "duplicate_count": int(cluster["duplicate_count"]),
        "update_count": int(cluster["update_count"]),
    }


def _scenario_db_path(scenario_id: str) -> Path:
    output_dir = Path(__file__).resolve().parents[2] / ".testdata"
    output_dir.mkdir(exist_ok=True)
    safe_id = re.sub(r"[^a-zA-Z0-9_.-]+", "-", scenario_id)
    db_path = output_dir / f"{safe_id}.sqlite3"
    if db_path.exists():
        db_path.unlink()
    return db_path
