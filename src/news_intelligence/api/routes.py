from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body, HTTPException

from news_intelligence.calibration.outcomes import JoinedOutcomeAnalysisService
from news_intelligence.calibration.service import HistoricalCalibrationService
from news_intelligence.ingestion.adapters import coerce_raw_news_items
from news_intelligence.intelligence import IntelligenceRefreshService
from news_intelligence.market_data.history import MarketDataHistoryBackfillService
from news_intelligence.market_data.service import MarketDataService
from news_intelligence.models import MarketDataInterval
from news_intelligence.outputs.file_drop import FileDropExporter
from news_intelligence.outputs.final_intelligence import FinalIntelligenceOutputService
from news_intelligence.pipeline import NewsIntelligencePipeline
from news_intelligence.progress import progress_store
from news_intelligence.schemas.export import public_json_schemas
from news_intelligence.sources.background import SourceAutomationBackgroundRunner
from news_intelligence.sources.eodhd_news import EodhdNewsConnector
from news_intelligence.sources.official_feeds import configured_official_feed_connectors
from news_intelligence.sources.scheduler import SourceScheduler
from news_intelligence.sources.sec_edgar import SecEdgarConnector
from news_intelligence.sources.service import SourceIngestionService
from news_intelligence.sources.world_news import WorldNewsConnector
from news_intelligence.storage.retention import StorageLayerSummaryService
from news_intelligence.universe import FavouritesUniverseService

router = APIRouter()
pipeline = NewsIntelligencePipeline()
automation_runner: SourceAutomationBackgroundRunner | None = None
NEWS_PAYLOAD = Body(...)
RETENTION_PAYLOAD = Body(default=None)
MARKET_DATA_PAYLOAD = Body(...)
MARKET_DATA_HISTORY_PAYLOAD = Body(...)
BACKFILL_PAYLOAD = Body(...)


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


@router.get("/universe/favourites")
async def favourites_universe() -> dict[str, Any]:
    return FavouritesUniverseService(pipeline.config).universe().model_dump(mode="json")


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


@router.post("/sources/world-news/poll")
async def poll_world_news(force: bool = False) -> dict[str, Any]:
    service = SourceIngestionService(pipeline)
    connector = WorldNewsConnector(pipeline.config)
    result = service.ingest(connector, force=force)
    return result.model_dump(mode="json")


@router.post("/sources/eodhd-news/poll")
async def poll_eodhd_news(force: bool = False) -> dict[str, Any]:
    service = SourceIngestionService(pipeline)
    connector = EodhdNewsConnector(pipeline.config, clock=pipeline.clock)
    result = service.ingest(connector, force=force)
    return result.model_dump(mode="json")


@router.post("/sources/official-feeds/poll")
async def poll_official_feeds(force: bool = False) -> list[dict[str, Any]]:
    service = SourceIngestionService(pipeline)
    runs = [
        service.ingest(connector, force=force)
        for connector in configured_official_feed_connectors(
            pipeline.config,
            clock=pipeline.clock,
        )
        if connector.enabled
    ]
    return [run.model_dump(mode="json") for run in runs]


@router.post("/sources/poll-due")
async def poll_due_sources(force: bool = False) -> list[dict[str, Any]]:
    runs = SourceScheduler(pipeline).poll_due(force=force)
    return [run.model_dump(mode="json") for run in runs]


@router.get("/sources/filings/recent")
async def recent_source_filings(limit: int = 50) -> list[dict[str, object]]:
    return SourceIngestionService(pipeline).recent_filings(limit=limit)


@router.get("/sources/items/recent")
async def recent_source_items(limit: int = 50) -> list[dict[str, object]]:
    return SourceIngestionService(pipeline).recent_filings(limit=limit)


@router.get("/sources/status")
async def source_status() -> list[dict[str, Any]]:
    statuses = pipeline.config.source_status()
    merged: dict[str, dict[str, Any]] = {
        f"{status.get('source_name')}:{status.get('connector_type')}": status
        for status in statuses
    }
    for status in SourceScheduler(pipeline).status()["sources"]:
        merged[f"{status.get('source_name')}:{status.get('connector_type')}"] = status
    return list(merged.values())


@router.get("/automation/status")
async def automation_status() -> dict[str, Any]:
    status = SourceScheduler(pipeline).status()
    status["background"] = (
        automation_runner.status()
        if automation_runner is not None
        else {
            "enabled": bool(pipeline.config.automation.get("enabled", False)),
            "running": False,
            "interval_seconds": SourceScheduler(pipeline).interval_seconds(),
            "last_tick_at": None,
            "next_tick_at": None,
            "last_error": None,
        }
    )
    return status


@router.post("/automation/run-now")
async def automation_run_now(force: bool = False) -> dict[str, Any]:
    if automation_runner is not None:
        return await automation_runner.run_once(
            reason="manual_api",
            force_sources=force,
        )
    return SourceScheduler(pipeline).run_once(
        force_sources=force,
        reason="manual_api",
    )


@router.get("/intelligence/output")
async def intelligence_output(limit: int = 500) -> dict[str, Any]:
    return FinalIntelligenceOutputService(
        pipeline.config,
        pipeline.repositories,
    ).list_output(limit=limit)


@router.post("/intelligence/refresh")
def intelligence_refresh(
    force: bool = False,
    export_delta: bool = True,
    limit: int = 500,
) -> dict[str, Any]:
    return IntelligenceRefreshService(pipeline).run(
        force_sources=force,
        export_delta=export_delta,
        limit=limit,
    )


@router.post("/intelligence/backfill")
def intelligence_backfill(payload: dict[str, Any] = BACKFILL_PAYLOAD) -> dict[str, Any]:
    try:
        start = _parse_date(str(payload["from"]))
        end = _parse_date(str(payload["to"]))
        source = str(payload.get("source", "eodhd_news"))
        limit = max(1, min(int(payload.get("limit", 5_000)), 50_000))
        page_limit = payload.get("page_limit")
        max_pages = payload.get("max_pages")
        return IntelligenceRefreshService(pipeline).backfill(
            start=start,
            end=end,
            source=source,
            export_delta=bool(payload.get("export_delta", True)),
            limit=limit,
            page_limit=int(page_limit) if page_limit is not None else None,
            max_pages=int(max_pages) if max_pages is not None else None,
        )
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=f"Missing required field: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Intelligence backfill failed: {exc}") from exc


@router.get("/intelligence/progress")
async def intelligence_progress(run_id: str | None = None) -> dict[str, Any]:
    progress = progress_store.get(run_id)
    if progress is None:
        return {
            "status": "idle",
            "phase": "idle",
            "message": "No intelligence run has started.",
        }
    return progress


@router.get("/calibration/report")
async def calibration_report(limit: int = 500) -> dict[str, Any]:
    service = HistoricalCalibrationService(
        pipeline.repositories,
        FavouritesUniverseService(pipeline.config),
    )
    return service.report(limit=limit)


@router.get("/calibration/outcomes")
async def calibration_outcomes(limit: int = 500) -> dict[str, Any]:
    service = JoinedOutcomeAnalysisService(
        pipeline.repositories,
        FavouritesUniverseService(pipeline.config),
    )
    return service.outcomes(limit=limit)


@router.post("/market-data/eodhd/fetch")
async def fetch_eodhd_market_data(
    payload: dict[str, Any] = MARKET_DATA_PAYLOAD,
) -> dict[str, Any]:
    try:
        symbol = str(payload["symbol"]).upper()
        exchange = str(payload["exchange"]).upper() if payload.get("exchange") else None
        interval = MarketDataInterval(str(payload.get("interval", "1d")))
        service = MarketDataService(
            pipeline.config,
            pipeline.repositories,
            clock=pipeline.clock,
        )
        if interval == MarketDataInterval.DAILY:
            start = _parse_date(str(payload["from"]))
            end = _parse_date(str(payload["to"]))
            return service.fetch_daily(
                symbol=symbol,
                exchange=exchange,
                start=start,
                end=end,
            )
        return service.fetch_intraday(
            symbol=symbol,
            exchange=exchange,
            interval=interval,
            start_at=_parse_datetime(str(payload["from"])),
            end_at=_parse_datetime(str(payload["to"])),
        )
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=f"Missing required field: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"EODHD market-data fetch failed: {exc}",
        ) from exc


@router.get("/market-data/bars/recent")
async def recent_market_bars(limit: int = 50) -> list[dict[str, Any]]:
    return MarketDataService(pipeline.config, pipeline.repositories).recent_bars(limit=limit)


@router.get("/market-data/requests/recent")
async def recent_market_data_requests(limit: int = 50) -> list[dict[str, Any]]:
    return MarketDataService(pipeline.config, pipeline.repositories).recent_requests(limit=limit)


@router.get("/market-data/coverage")
async def market_data_coverage() -> dict[str, Any]:
    return MarketDataService(pipeline.config, pipeline.repositories).coverage_summary()


@router.post("/market-data/eodhd/backfill")
def populate_eodhd_market_data_history(
    payload: dict[str, Any] = MARKET_DATA_HISTORY_PAYLOAD,
) -> dict[str, Any]:
    try:
        start = _parse_date(str(payload["from"]))
        end = _parse_date(str(payload["to"]))
        symbols_payload = payload.get("symbols")
        symbols = (
            [str(symbol).upper() for symbol in symbols_payload if symbol]
            if isinstance(symbols_payload, list)
            else None
        )
        max_symbols = payload.get("max_symbols")
        return MarketDataHistoryBackfillService(
            pipeline.config,
            pipeline.repositories,
            clock=pipeline.clock,
        ).populate_daily_history(
            start=start,
            end=end,
            include_benchmarks=bool(payload.get("include_benchmarks", True)),
            symbols=symbols,
            max_symbols=int(max_symbols) if max_symbols is not None else None,
        )
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=f"Missing required field: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"EODHD market-data history backfill failed: {exc}",
        ) from exc


@router.get("/outputs/file-drop/status")
async def file_drop_status() -> dict[str, Any]:
    return FileDropExporter(pipeline.config, pipeline.repositories).status()


@router.get("/storage/layers")
async def storage_layers() -> dict[str, Any]:
    return StorageLayerSummaryService(pipeline.config, pipeline.repositories).summary()


@router.post("/storage/retention/dry-run")
async def storage_retention_dry_run(
    payload: dict[str, Any] | None = RETENTION_PAYLOAD,
) -> dict[str, Any]:
    retention_days = payload.get("retention_days", {}) if isinstance(payload, dict) else {}
    return StorageLayerSummaryService(
        pipeline.config,
        pipeline.repositories,
        clock=pipeline.clock,
    ).retention_plan(retention_days)


@router.post("/storage/retention/apply")
async def storage_retention_apply(
    payload: dict[str, Any] | None = RETENTION_PAYLOAD,
) -> dict[str, Any]:
    retention_days = payload.get("retention_days", {}) if isinstance(payload, dict) else {}
    return StorageLayerSummaryService(
        pipeline.config,
        pipeline.repositories,
        clock=pipeline.clock,
    ).apply_retention(retention_days)


@router.post("/outputs/file-drop/signals/{signal_id}")
async def export_signal_to_file_drop(signal_id: str) -> dict[str, Any]:
    try:
        return FileDropExporter(pipeline.config, pipeline.repositories).export_signal(signal_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Signal not found") from exc


@router.post("/outputs/file-drop/latest")
async def export_latest_to_file_drop(limit: int = 20) -> list[dict[str, Any]]:
    return FileDropExporter(pipeline.config, pipeline.repositories).export_latest(limit=limit)


def _parse_date(value: str) -> date:
    return date.fromisoformat(value[:10])


def _parse_datetime(value: str) -> datetime:
    candidate = value.strip()
    if candidate.endswith("Z"):
        candidate = f"{candidate[:-1]}+00:00"
    return datetime.fromisoformat(candidate)


@router.get("/schemas")
async def schemas() -> dict[str, Any]:
    return public_json_schemas()
