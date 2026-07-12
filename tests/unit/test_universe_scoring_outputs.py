from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from news_intelligence.calibration.service import HistoricalCalibrationService
from news_intelligence.config import load_config
from news_intelligence.ingestion.adapters import coerce_raw_news_items
from news_intelligence.outputs.file_drop import FileDropExporter
from news_intelligence.pipeline import NewsIntelligencePipeline
from news_intelligence.sources.service import SourceIngestionService
from news_intelligence.sources.world_news import WorldNewsConnector
from news_intelligence.storage import RepositoryBundle
from news_intelligence.universe import FavouritesUniverseService

FIXED_NOW = datetime(2026, 7, 11, 12, 0, tzinfo=UTC)
EARNINGS_BODY = "Revenue and earnings exceeded expectations and forward guidance was increased."


def test_favourites_universe_contains_lse_aliases() -> None:
    universe = FavouritesUniverseService(load_config()).universe()
    symbols = {instrument.symbol for instrument in universe.instruments}
    semg = next(instrument for instrument in universe.instruments if instrument.symbol == "SEMG.L")

    assert "NVDA" in symbols
    assert "SEMG.L" in symbols
    assert "QNTG.L" in symbols
    assert semg.uk_lse_gbp_etf is True
    assert "SEMG" in semg.aliases


def test_signal_contract_exposes_score_composition_and_risk(isolated_database: Path) -> None:
    pipeline = NewsIntelligencePipeline(
        repositories=RepositoryBundle(isolated_database),
        clock=lambda: FIXED_NOW,
    )
    result = pipeline.analyse(
        coerce_raw_news_items(
            {
                "headline": "NVIDIA reports earnings above expectations and raises guidance",
                "body": EARNINGS_BODY,
                "source_name": "Example Newswire",
                "published_at": "2026-07-11T09:14:00Z",
                "known_ticker": "NVDA",
                "source_article_id": "nvda-rich-signal-001",
            }
        ),
        persist=True,
    )
    signal = next(item for item in result.signals if item.instrument.symbol == "NVDA")

    assert signal.signal.signal_score > 0
    assert signal.signal.strength.value in {
        "WEAK_BULLISH",
        "BULLISH",
        "STRONG_BULLISH",
    }
    assert signal.classification.indicator_category.value == "event_intelligence"
    assert signal.composition.source_credibility > 0
    assert signal.risk.rumour_risk == 0
    assert signal.evidence.update_count == 0


def test_world_news_connector_ingests_once_and_classifies(isolated_database: Path) -> None:
    pipeline = NewsIntelligencePipeline(
        repositories=RepositoryBundle(isolated_database),
        clock=lambda: FIXED_NOW,
    )
    service = SourceIngestionService(pipeline)
    connector = WorldNewsConnector(pipeline.config)

    first = service.ingest(connector, force=True)
    second = service.ingest(connector, force=True)

    assert first.ingested_count == 2
    assert second.ingested_count == 0
    assert second.skipped_count == 0
    assert pipeline.repositories.source_filings.list_all()
    assert any(
        event["event_type"] == "geopolitical"
        for event in pipeline.repositories.events.list_recent(20)
    )


def test_calibration_report_is_scoped_to_favourites(isolated_database: Path) -> None:
    pipeline = NewsIntelligencePipeline(
        repositories=RepositoryBundle(isolated_database),
        clock=lambda: FIXED_NOW,
    )
    pipeline.analyse(
        coerce_raw_news_items(
            {
                "headline": "NVIDIA reports earnings above expectations and raises guidance",
                "body": EARNINGS_BODY,
                "source_name": "Example Newswire",
                "published_at": "2026-07-11T09:14:00Z",
                "known_ticker": "NVDA",
                "source_article_id": "nvda-calibration-001",
            }
        ),
        persist=True,
    )
    report = HistoricalCalibrationService(
        pipeline.repositories,
        FavouritesUniverseService(pipeline.config),
    ).report()

    assert report["favourites_count"] > 0
    assert report["signal_count"] >= 1
    assert report["outcome_status"] == "pending_market_data_join"
    assert "20d" in report["outcome_windows"]


def test_file_drop_exports_atomic_json_payload(
    isolated_database: Path,
) -> None:
    pipeline = NewsIntelligencePipeline(
        repositories=RepositoryBundle(isolated_database),
        clock=lambda: FIXED_NOW,
    )
    pipeline.analyse(
        coerce_raw_news_items(
            {
                "headline": "NVIDIA reports earnings above expectations and raises guidance",
                "body": EARNINGS_BODY,
                "source_name": "Example Newswire",
                "published_at": "2026-07-11T09:14:00Z",
                "known_ticker": "NVDA",
                "source_article_id": "nvda-file-drop-001",
            }
        ),
        persist=True,
    )
    signal_id = pipeline.repositories.signals.list_recent(1)[0]["signal_id"]
    output_dir = isolated_database.parent / f"file_drop_{isolated_database.stem}"
    settings = dict(pipeline.config.file_drop)
    settings["output_dir"] = str(output_dir)
    config = replace(pipeline.config, file_drop=settings)

    exported = FileDropExporter(config, pipeline.repositories).export_signal(signal_id)

    assert exported["path"].endswith(".json")
    assert Path(str(exported["path"])).exists()
    assert exported["payload"]["producer"] == "asterius_news_intelligence"
    assert exported["payload"]["signal"]["signal_id"] == signal_id
