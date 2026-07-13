from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

from news_intelligence.config import NewsIntelligenceConfig, load_config
from news_intelligence.market_data.eodhd import EodhdMarketDataClient
from news_intelligence.market_data.history import MarketDataHistoryBackfillService
from news_intelligence.market_data.service import MarketDataService
from news_intelligence.market_data.timing import EventMarketTimer
from news_intelligence.models import (
    MarketDataBar,
    MarketDataInterval,
    MarketSession,
    RuntimeEnvironment,
)
from news_intelligence.progress import progress_store
from news_intelligence.storage import RepositoryBundle
from news_intelligence.storage.retention import StorageLayerSummaryService

FIXED_NOW = datetime(2026, 7, 12, 12, 0, tzinfo=UTC)


def test_eodhd_client_converts_daily_bars_and_symbols() -> None:
    urls: list[str] = []
    client = EodhdMarketDataClient(
        _eodhd_config(),
        fetcher=_daily_fetcher(urls),
        clock=lambda: FIXED_NOW,
    )

    bars = client.fetch_daily_bars(
        symbol="AAPL",
        exchange="NASDAQ",
        start=date(2026, 7, 1),
        end=date(2026, 7, 2),
    )

    assert client.eodhd_symbol("AAPL", "NASDAQ") == "AAPL.US"
    assert client.eodhd_symbol("SEMG.L", "LSE") == "SEMG.LSE"
    assert client.eodhd_symbol("000660") == "000660.KO"
    assert client.eodhd_symbol("002594") == "002594.SHE"
    assert client.eodhd_symbol("005490") == "005490.KO"
    assert client.eodhd_symbol("005935") == "005935.KO"
    assert client.eodhd_symbol("SANN") == "SANN.SW"
    assert client.eodhd_symbol("VIX", "CBOE") == "VIX.INDX"
    assert len(bars) == 2
    assert bars[0].symbol == "AAPL"
    assert bars[0].interval == MarketDataInterval.DAILY
    assert bars[0].timestamp_utc == datetime(2026, 7, 1, tzinfo=UTC)
    assert bars[0].adjusted_close == 101.5
    assert "api_token=dummy-token" in urls[0]


def test_market_data_service_stores_bars_once_and_audits_request(
    isolated_database: Path,
) -> None:
    repositories = RepositoryBundle(isolated_database)
    client = EodhdMarketDataClient(
        _eodhd_config(),
        fetcher=_daily_fetcher([]),
        clock=lambda: FIXED_NOW,
    )
    service = MarketDataService(
        _eodhd_config(),
        repositories,
        client=client,
        clock=lambda: FIXED_NOW,
    )

    first = service.fetch_daily(
        symbol="AAPL",
        exchange="NASDAQ",
        start=date(2026, 7, 1),
        end=date(2026, 7, 2),
    )
    second = service.fetch_daily(
        symbol="AAPL",
        exchange="NASDAQ",
        start=date(2026, 7, 1),
        end=date(2026, 7, 2),
    )
    bars = repositories.market_bars.list_range(
        symbol="AAPL",
        exchange="NASDAQ",
        interval=MarketDataInterval.DAILY,
        start_at=datetime(2026, 7, 1, tzinfo=UTC),
        end_at=datetime(2026, 7, 2, tzinfo=UTC),
    )
    request = repositories.market_data_requests.list_recent(1)[0]
    coverage = service.coverage_summary()
    coverage_row = next(
        row for row in coverage["rows"] if row["symbol"] == "AAPL" and row["interval"] == "1d"
    )

    assert first["records_stored"] == 2
    assert second["records_stored"] == 2
    assert len(bars) == 2
    assert request["estimated_api_call_cost"] == 1
    assert "dummy-token" not in json.dumps(request)
    assert coverage["total_bar_count"] == 2
    assert coverage_row["bar_count"] == 2
    assert coverage_row["first_timestamp_utc"] == "2026-07-01T00:00:00+00:00"
    assert coverage_row["last_timestamp_utc"] == "2026-07-02T00:00:00+00:00"
    assert coverage_row["last_request_status"] == "success"


def test_market_data_mapping_summary_exposes_overrides_and_failures(
    isolated_database: Path,
) -> None:
    repositories = RepositoryBundle(isolated_database)
    service = MarketDataService(_eodhd_config(), repositories, clock=lambda: FIXED_NOW)
    repositories.market_data_requests.save(
        "failed-005490",
        {
            "request_id": "failed-005490",
            "symbol": "005490",
            "exchange": None,
            "interval": "1d",
            "requested_at": FIXED_NOW.isoformat(),
            "status": "failed",
            "error": "EODHD request failed: HTTP 404",
        },
    )

    summary = service.mapping_summary()
    overrides = {
        row["symbol"]: row["provider_symbol"] for row in summary["symbol_overrides"]
    }
    failure = summary["recent_failures"][0]

    assert overrides["005490"] == "005490.KO"
    assert overrides["002594"] == "002594.SHE"
    assert overrides["005935"] == "005935.KO"
    assert failure["symbol"] == "005490"
    assert failure["configured_symbol"] is False
    assert failure["current_provider_symbol"] == "005490.KO"
    assert failure["failure_kind"] == "provider_not_found"
    assert failure["mapping_status"] == "provider_override"


def test_market_data_history_backfill_populates_universe_symbols(
    isolated_database: Path,
) -> None:
    repositories = RepositoryBundle(isolated_database)
    config = _eodhd_config()
    client = EodhdMarketDataClient(
        config,
        fetcher=_daily_fetcher([]),
        clock=lambda: FIXED_NOW,
    )
    market_data = MarketDataService(
        config,
        repositories,
        client=client,
        clock=lambda: FIXED_NOW,
    )
    service = MarketDataHistoryBackfillService(
        config,
        repositories,
        clock=lambda: FIXED_NOW,
        market_data_service=market_data,
    )

    first = service.populate_daily_history(
        start=date(2026, 7, 1),
        end=date(2026, 7, 2),
        include_benchmarks=False,
        symbols=["NVDA"],
    )
    second = service.populate_daily_history(
        start=date(2026, 7, 1),
        end=date(2026, 7, 2),
        include_benchmarks=False,
        symbols=["NVDA"],
    )
    explicit_benchmark = service.populate_daily_history(
        start=date(2026, 7, 1),
        end=date(2026, 7, 2),
        include_benchmarks=False,
        symbols=["ACWI"],
    )
    bars = repositories.market_bars.list_range(
        symbol="NVDA",
        exchange="NASDAQ",
        interval=MarketDataInterval.DAILY,
        start_at=datetime(2026, 7, 1, tzinfo=UTC),
        end_at=datetime(2026, 7, 2, tzinfo=UTC),
    )
    benchmark_bars = repositories.market_bars.list_range(
        symbol="ACWI",
        exchange=None,
        interval=MarketDataInterval.DAILY,
        start_at=datetime(2026, 7, 1, tzinfo=UTC),
        end_at=datetime(2026, 7, 2, tzinfo=UTC),
    )
    progress = progress_store.get(str(first["automation_run_id"]))

    assert first["records_stored"] == 2
    assert first["request_count"] == 1
    assert second["request_count"] == 0
    assert second["skipped_count"] == 1
    assert explicit_benchmark["records_stored"] == 2
    assert len(bars) == 2
    assert len(benchmark_bars) == 2
    assert progress is not None
    assert progress["status"] == "complete"


def test_market_data_layers_are_retention_managed(isolated_database: Path) -> None:
    repositories = RepositoryBundle(isolated_database)
    repositories.market_bars.save_many(
        [
            _bar("AAPL", MarketDataInterval.DAILY, "2026-05-01T00:00:00+00:00"),
            _bar(
                "MSFT",
                MarketDataInterval.DAILY,
                "2026-05-02T00:00:00+00:00",
                environment=RuntimeEnvironment.PRODUCTION,
            ),
            _bar("NVDA", MarketDataInterval.FIVE_MINUTE, "2026-05-01T13:30:00+00:00"),
            _bar("AAPL", MarketDataInterval.DAILY, "2026-07-10T00:00:00+00:00"),
        ]
    )
    service = StorageLayerSummaryService(
        load_config(),
        repositories,
        clock=lambda: FIXED_NOW,
    )

    summary = service.summary()
    layers = {str(layer["layer_key"]): layer for layer in summary["layers"]}
    applied = service.apply_retention(
        {
            "market_daily_bars": 30,
            "market_intraday_bars": 30,
        }
    )
    daily_plan = _retention_layer(applied, "market_daily_bars")
    intraday_plan = _retention_layer(applied, "market_intraday_bars")

    remaining_daily = repositories.market_bars.list_range(
        symbol="AAPL",
        exchange="NASDAQ",
        interval=MarketDataInterval.DAILY,
        start_at=datetime(2026, 1, 1, tzinfo=UTC),
        end_at=datetime(2026, 12, 31, tzinfo=UTC),
    )

    assert layers["market_daily_bars"]["record_count"] == 3
    assert layers["market_intraday_bars"]["record_count"] == 1
    assert layers["market_daily_bars"]["adjustable"] is True
    assert daily_plan["deleted_records"] == 1
    assert daily_plan["skipped_production_records"] == 1
    assert intraday_plan["deleted_records"] == 1
    assert len(remaining_daily) == 1
    assert remaining_daily[0].timestamp_utc == datetime(2026, 7, 10, tzinfo=UTC)


def test_event_market_timer_handles_after_hours_weekends_and_cached_bars() -> None:
    timer = EventMarketTimer()
    after_hours = datetime(2026, 7, 10, 20, 31, tzinfo=UTC)

    calendar_anchor = timer.anchor_event(event_at=after_hours, exchange="NASDAQ")
    cached_bar_anchor = timer.anchor_event(
        event_at=after_hours,
        exchange="NASDAQ",
        available_bars=[
            _bar("AAPL", MarketDataInterval.FIVE_MINUTE, "2026-07-10T20:35:00+00:00")
        ],
    )
    weekend_anchor = timer.anchor_event(
        event_at=datetime(2026, 7, 11, 12, 0, tzinfo=UTC),
        exchange="NASDAQ",
    )

    assert calendar_anchor.session == MarketSession.AFTER_HOURS
    assert calendar_anchor.market_anchor_at == datetime(2026, 7, 13, 13, 30, tzinfo=UTC)
    assert cached_bar_anchor.anchor_source == "available_bar"
    assert cached_bar_anchor.market_anchor_at == datetime(2026, 7, 10, 20, 35, tzinfo=UTC)
    assert weekend_anchor.session == MarketSession.WEEKEND
    assert weekend_anchor.market_anchor_at == datetime(2026, 7, 13, 13, 30, tzinfo=UTC)


def _eodhd_config() -> NewsIntelligenceConfig:
    base = load_config()
    return replace(
        base,
        eodhd={
            **base.eodhd,
            "enabled": True,
            "api_token": "dummy-token",
            "api_token_env": "EODHD_TEST_UNUSED",
            "rate_limit_per_minute": 60_000,
        },
    )


def _daily_fetcher(urls: list[str]) -> Callable[[str, dict[str, str], int], str]:
    def fetch(url: str, _headers: dict[str, str], _timeout: int) -> str:
        urls.append(url)
        return json.dumps(
            [
                {
                    "date": "2026-07-01",
                    "open": 100,
                    "high": 103,
                    "low": 99,
                    "close": 102,
                    "adjusted_close": 101.5,
                    "volume": 1200000,
                },
                {
                    "date": "2026-07-02",
                    "open": 102,
                    "high": 104,
                    "low": 101,
                    "close": 103,
                    "adjusted_close": 102.5,
                    "volume": 1300000,
                },
            ]
        )

    return fetch


def _bar(
    symbol: str,
    interval: MarketDataInterval,
    timestamp: str,
    *,
    environment: RuntimeEnvironment = RuntimeEnvironment.DEVELOPMENT,
) -> MarketDataBar:
    return MarketDataBar(
        symbol=symbol,
        exchange="NASDAQ",
        interval=interval,
        timestamp_utc=datetime.fromisoformat(timestamp),
        open=100,
        high=101,
        low=99,
        close=100.5,
        adjusted_close=100.5 if interval == MarketDataInterval.DAILY else None,
        volume=1000000,
        loaded_at=FIXED_NOW,
        record_environment=environment,
    )


def _retention_layer(plan: dict[str, object], layer_key: str) -> dict[str, object]:
    layers = plan["layers"]
    assert isinstance(layers, list)
    layer = next(item for item in layers if item["layer_key"] == layer_key)
    assert isinstance(layer, dict)
    return layer
