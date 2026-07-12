from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body, HTTPException

from news_intelligence.ingestion.adapters import coerce_raw_news_items
from news_intelligence.pipeline import NewsIntelligencePipeline
from news_intelligence.schemas.export import public_json_schemas
from news_intelligence.sources.sec_edgar import SecEdgarConnector
from news_intelligence.sources.service import SourceIngestionService

router = APIRouter()
pipeline = NewsIntelligencePipeline()
NEWS_PAYLOAD = Body(...)


@router.post("/news/analyse")
async def analyse_news(payload: Any = NEWS_PAYLOAD) -> dict[str, Any]:
    try:
        raw_items = coerce_raw_news_items(payload)
        result = pipeline.analyse(raw_items, persist=True)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"News analysis failed: {exc}") from exc
    return result.model_dump(mode="json")


@router.post("/news/events")
async def create_news_event(payload: Any = NEWS_PAYLOAD) -> dict[str, Any]:
    return await analyse_news(payload)


@router.get("/news/events/recent")
async def recent_events(limit: int = 50) -> list[dict[str, Any]]:
    return pipeline.recent_events(limit=limit)


@router.get("/news/events/{event_id}/detail")
async def get_event_detail(event_id: str) -> dict[str, Any]:
    event = pipeline.get_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    cluster_id = str(event.get("cluster_id", ""))
    cluster = pipeline.get_cluster(cluster_id) if cluster_id else None
    impacts = [
        impact
        for impact in pipeline.repositories.impacts.list_recent(500)
        if impact.get("event_id") == event_id or impact.get("cluster_id") == cluster_id
    ]
    signals = [
        signal
        for signal in pipeline.repositories.signals.list_recent(500)
        if signal.get("event_id") == event_id or signal.get("cluster_id") == cluster_id
    ]
    return {"event": event, "cluster": cluster, "impacts": impacts, "signals": signals}


@router.get("/news/events/{event_id}")
async def get_event(event_id: str) -> dict[str, Any]:
    event = pipeline.get_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@router.get("/news/clusters/{cluster_id}")
async def get_cluster(cluster_id: str) -> dict[str, Any]:
    cluster = pipeline.get_cluster(cluster_id)
    if cluster is None:
        raise HTTPException(status_code=404, detail="Cluster not found")
    return cluster


@router.get("/news/signals/{symbol}")
async def get_signals(symbol: str, limit: int = 20) -> list[dict[str, Any]]:
    return pipeline.get_signals(symbol.upper())[:limit]


@router.post("/test-runs")
async def create_test_run() -> dict[str, Any]:
    return {
        "test_run_id": f"test_run_{uuid4().hex[:12]}",
        "record_environment": "test",
    }


@router.get("/test-runs")
async def list_test_runs() -> list[dict[str, Any]]:
    runs: dict[str, dict[str, Any]] = {}
    for cluster in pipeline.repositories.clusters.list_recent(1000):
        test_run_id = cluster.get("test_run_id")
        if not test_run_id:
            continue
        run = runs.setdefault(
            str(test_run_id),
            {
                "test_run_id": test_run_id,
                "record_environment": cluster.get("record_environment", "test"),
                "cluster_count": 0,
                "article_count": 0,
                "latest_article_at": None,
            },
        )
        run["cluster_count"] += 1
        run["article_count"] += int(cluster.get("article_count", 0))
        latest_article_at = cluster.get("latest_article_at")
        if latest_article_at and (
            run["latest_article_at"] is None or latest_article_at > run["latest_article_at"]
        ):
            run["latest_article_at"] = latest_article_at
    return sorted(runs.values(), key=lambda run: str(run["latest_article_at"]), reverse=True)


@router.delete("/test-runs/{test_run_id}")
async def delete_test_run(test_run_id: str) -> dict[str, Any]:
    deleted = pipeline.repositories.delete_test_run(test_run_id)
    return {"test_run_id": test_run_id, "deleted": deleted}


@router.delete("/development-data")
async def delete_development_data() -> dict[str, Any]:
    return {"deleted": pipeline.repositories.delete_development_data()}


@router.post("/sources/sec-edgar/poll")
async def poll_sec_edgar(force: bool = False) -> dict[str, Any]:
    service = SourceIngestionService(pipeline)
    connector = SecEdgarConnector(pipeline.config, clock=pipeline.clock)
    result = service.ingest(connector, force=force)
    return result.model_dump(mode="json")


@router.get("/sources/filings/recent")
async def recent_source_filings(limit: int = 50) -> list[dict[str, object]]:
    return SourceIngestionService(pipeline).recent_filings(limit=limit)


@router.get("/sources/status")
async def source_status() -> list[dict[str, Any]]:
    statuses = pipeline.config.source_status()
    service = SourceIngestionService(pipeline)
    sec_status = service.status_for(SecEdgarConnector(pipeline.config, clock=pipeline.clock))
    merged: dict[str, dict[str, Any]] = {
        f"{status.get('source_name')}:{status.get('connector_type')}": status
        for status in statuses
    }
    merged[f"{sec_status.source_name}:{sec_status.connector_type}"] = sec_status.model_dump(
        mode="json"
    )
    return list(merged.values())



@router.get("/schemas")
async def schemas() -> dict[str, Any]:
    return public_json_schemas()
