from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from news_intelligence.calibration.outcomes import JoinedOutcomeAnalysisService
from news_intelligence.ingestion.adapters import coerce_raw_news_items
from news_intelligence.models import MarketDataBar, MarketDataInterval
from news_intelligence.pipeline import NewsIntelligencePipeline
from news_intelligence.storage import RepositoryBundle
from news_intelligence.universe import FavouritesUniverseService

FIXED_NOW = datetime(2026, 7, 12, 12, 0, tzinfo=UTC)


def test_joined_outcomes_calculate_forward_and_abnormal_returns(
    isolated_database: Path,
) -> None:
    pipeline = _pipeline(isolated_database)
    pipeline.analyse(
        coerce_raw_news_items(
            {
                "headline": "NVIDIA reports earnings above expectations and raises guidance",
                "body": (
                    "Revenue and earnings exceeded expectations and forward guidance was increased."
                ),
                "source_name": "Example Newswire",
                "published_at": "2026-07-10T14:00:00Z",
                "known_ticker": "NVDA",
                "source_article_id": "nvda-outcome-001",
            }
        ),
        persist=True,
    )
    pipeline.repositories.market_bars.save_many(
        [
            _bar("NVDA", MarketDataInterval.FIVE_MINUTE, "2026-07-10T14:00:00+00:00", 100),
            _bar("NVDA", MarketDataInterval.FIVE_MINUTE, "2026-07-10T14:30:00+00:00", 103),
            _bar("NVDA", MarketDataInterval.FIVE_MINUTE, "2026-07-10T15:00:00+00:00", 104),
            _bar("SMH", MarketDataInterval.FIVE_MINUTE, "2026-07-10T14:00:00+00:00", 50),
            _bar("SMH", MarketDataInterval.FIVE_MINUTE, "2026-07-10T14:30:00+00:00", 50.5),
            *[
                _bar("NVDA", MarketDataInterval.DAILY, timestamp, close)
                for timestamp, close in [
                    ("2026-07-10T00:00:00+00:00", 105),
                    ("2026-07-13T00:00:00+00:00", 107),
                    ("2026-07-14T00:00:00+00:00", 108),
                    ("2026-07-15T00:00:00+00:00", 109),
                    ("2026-07-16T00:00:00+00:00", 110),
                    ("2026-07-17T00:00:00+00:00", 112),
                ]
            ],
            *[
                _bar("SMH", MarketDataInterval.DAILY, timestamp, close)
                for timestamp, close in [
                    ("2026-07-10T00:00:00+00:00", 51),
                    ("2026-07-13T00:00:00+00:00", 51.5),
                    ("2026-07-14T00:00:00+00:00", 52),
                    ("2026-07-15T00:00:00+00:00", 52.5),
                    ("2026-07-16T00:00:00+00:00", 53),
                    ("2026-07-17T00:00:00+00:00", 53.5),
                ]
            ],
        ]
    )

    report = JoinedOutcomeAnalysisService(
        pipeline.repositories,
        FavouritesUniverseService(pipeline.config),
    ).outcomes()
    row = next(item for item in report["rows"] if item["symbol"] == "NVDA")

    assert report["outcome_status"] == "ready"
    assert report["outcome_count"] >= 1
    assert row["price_at_event"] == 100
    assert row["returns"]["30m"] == 0.03
    assert row["benchmark_returns"]["30m"] == 0.01
    assert row["abnormal_returns"]["30m"] == 0.02
    assert row["returns"]["1d"] == 0.07
    assert row["outcome_status"] in {"partial", "complete"}
    assert row["market_session"] == "REGULAR_SESSION"


def test_joined_outcomes_expose_missing_market_data(
    isolated_database: Path,
) -> None:
    pipeline = _pipeline(isolated_database)
    pipeline.analyse(
        coerce_raw_news_items(
            {
                "headline": "NVIDIA reports earnings above expectations and raises guidance",
                "body": (
                    "Revenue and earnings exceeded expectations and forward guidance was increased."
                ),
                "source_name": "Example Newswire",
                "published_at": "2026-07-10T14:00:00Z",
                "known_ticker": "NVDA",
                "source_article_id": "nvda-outcome-missing-data",
            }
        ),
        persist=True,
    )

    report = JoinedOutcomeAnalysisService(
        pipeline.repositories,
        FavouritesUniverseService(pipeline.config),
    ).outcomes()
    row = next(item for item in report["rows"] if item["symbol"] == "NVDA")

    assert report["outcome_status"] == "pending_market_data_join"
    assert report["missing_market_data_count"] >= 1
    assert row["outcome_status"] == "missing_market_data"
    assert row["returns"]["30m"] is None
    assert row["confounder_grade"] == "unusable"


def _pipeline(database_path: Path) -> NewsIntelligencePipeline:
    return NewsIntelligencePipeline(
        repositories=RepositoryBundle(database_path),
        clock=lambda: FIXED_NOW,
    )


def _bar(
    symbol: str,
    interval: MarketDataInterval,
    timestamp: str,
    close: float,
) -> MarketDataBar:
    return MarketDataBar(
        symbol=symbol,
        exchange="NASDAQ",
        interval=interval,
        timestamp_utc=datetime.fromisoformat(timestamp),
        open=close,
        high=close + 1,
        low=close - 1,
        close=close,
        adjusted_close=close if interval == MarketDataInterval.DAILY else None,
        volume=1_000_000,
        loaded_at=FIXED_NOW,
    )
