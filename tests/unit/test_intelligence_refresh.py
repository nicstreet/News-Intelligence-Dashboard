from __future__ import annotations

import json
import urllib.parse
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from news_intelligence.config import load_config
from news_intelligence.ingestion.adapters import coerce_raw_news_items
from news_intelligence.intelligence import IntelligenceRefreshService
from news_intelligence.models import MarketDataBar, MarketDataInterval
from news_intelligence.outputs.final_intelligence import FinalIntelligenceOutputService
from news_intelligence.pipeline import NewsIntelligencePipeline
from news_intelligence.progress import progress_store
from news_intelligence.sources.eodhd_news import EodhdNewsConnector
from news_intelligence.sources.official_feeds import OfficialFeedConnector
from news_intelligence.storage import RepositoryBundle

FIXED_NOW = datetime(2026, 7, 12, 12, 0, tzinfo=UTC)
BODY = "Revenue and earnings exceeded expectations and forward guidance was increased."


def test_final_intelligence_exports_only_changed_delta(
    isolated_database: Path,
) -> None:
    pipeline = _pipeline(isolated_database)
    pipeline.analyse(
        coerce_raw_news_items(
            {
                "headline": "NVIDIA reports earnings above expectations and raises guidance",
                "body": BODY,
                "source_name": "Example Newswire",
                "published_at": "2026-07-10T14:00:00Z",
                "known_ticker": "NVDA",
                "source_article_id": "nvda-final-output",
            }
        ),
        persist=True,
    )
    pipeline.repositories.market_bars.save_many(
        [
            _bar("NVDA", "2026-07-10T00:00:00+00:00", 100),
            _bar("NVDA", "2026-07-13T00:00:00+00:00", 104),
            _bar("SMH", "2026-07-10T00:00:00+00:00", 50),
            _bar("SMH", "2026-07-13T00:00:00+00:00", 51),
        ]
    )
    output_dir = isolated_database.parent / "outbox"
    config = replace(
        pipeline.config,
        file_drop={**pipeline.config.file_drop, "output_dir": str(output_dir)},
    )
    service = FinalIntelligenceOutputService(config, pipeline.repositories)

    first = service.export_delta(run_id="run_one")
    second = service.export_delta(run_id="run_two")

    assert first["records_exported"] >= 1
    assert second["records_exported"] == 0
    assert (output_dir / "run_one_manifest.json").exists()
    assert (output_dir / "run_two_manifest.json").exists()
    assert pipeline.repositories.final_outputs.list_recent(10)


def test_intelligence_refresh_returns_clean_output(
    isolated_database: Path,
) -> None:
    pipeline = _pipeline(isolated_database)
    pipeline.analyse(
        coerce_raw_news_items(
            {
                "headline": "NVIDIA reports earnings above expectations and raises guidance",
                "body": BODY,
                "source_name": "Example Newswire",
                "published_at": "2026-07-10T14:00:00Z",
                "known_ticker": "NVDA",
                "source_article_id": "nvda-refresh-output",
            }
        ),
        persist=True,
    )

    result = IntelligenceRefreshService(pipeline).run(force_sources=False, export_delta=False)

    assert result["final_record_count"] >= 1
    assert result["output"]["records"][0]["record_id"].startswith("intel_")
    assert result["exported_count"] == 0


def test_eodhd_news_connector_maps_payload_to_raw_item() -> None:
    config = replace(
        load_config(),
        eodhd={
            **load_config().eodhd,
            "api_token": "dummy-token",
            "news": {
                "enabled": True,
                "limit": 10,
                "symbols": ["NVDA"],
                "rate_limit_per_minute": 60_000,
            },
        },
    )
    connector = EodhdNewsConnector(
        config,
        fetcher=lambda _url, _headers, _timeout: json.dumps(
            [
                {
                    "title": "NVIDIA announces new AI platform",
                    "date": "2026-07-10T14:00:00+00:00",
                    "link": "https://example.test/nvda",
                    "content": "NVIDIA introduced a new data-centre AI platform.",
                    "symbols": ["NVDA.US"],
                }
            ]
        ),
        clock=lambda: FIXED_NOW,
    )

    record = connector.fetch(set())[0]
    raw = connector.to_raw_news_item(record)

    assert record.source_record_id.startswith("eodhd_news:")
    assert raw.known_ticker == "NVDA"
    assert raw.source.source_name == "EODHD Financial News"


def test_eodhd_news_connector_fetches_historical_range_pages() -> None:
    config = replace(
        load_config(),
        eodhd={
            **load_config().eodhd,
            "api_token": "dummy-token",
            "news": {
                "enabled": True,
                "limit": 2,
                "symbols": ["NVDA"],
                "rate_limit_per_minute": 60_000,
            },
        },
    )
    requested_urls: list[str] = []

    def fetcher(url: str, _headers: dict[str, str], _timeout: int) -> str:
        requested_urls.append(url)
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        offset = int(query["offset"][0])
        assert query["from"][0] == "2021-01-01"
        assert query["to"][0] == "2021-12-31"
        assert "s" not in query
        if offset == 0:
            return json.dumps(
                [
                    {
                        "id": "old-2",
                        "title": "NVIDIA confirms product update",
                        "date": "2021-01-02T14:00:00+00:00",
                        "symbols": ["NVDA.US"],
                    },
                    {
                        "id": "old-1",
                        "title": "NVIDIA announces product update",
                        "date": "2021-01-01T14:00:00+00:00",
                        "symbols": ["NVDA.US"],
                    },
                ]
            )
        return json.dumps(
            [
                {
                    "id": "old-3",
                    "title": "NVIDIA expands product update",
                    "date": "2021-01-03T14:00:00+00:00",
                    "symbols": ["NVDA.US"],
                }
            ]
        )

    connector = EodhdNewsConnector(config, fetcher=fetcher, clock=lambda: FIXED_NOW)

    records = connector.fetch_range(
        start=date(2021, 1, 1),
        end=date(2021, 12, 31),
        limit=2,
        max_pages=3,
    )

    assert [record.source_record_id for record in records] == ["old-1", "old-2", "old-3"]
    assert len(requested_urls) == 2


def test_intelligence_backfill_runs_range_through_pipeline(
    isolated_database: Path,
    monkeypatch: Any,
) -> None:
    base = load_config()
    output_dir = isolated_database.parent / "backfill_outbox"
    config = replace(
        base,
        eodhd={
            **base.eodhd,
            "api_token": "dummy-token",
            "news": {
                "enabled": True,
                "limit": 50,
                "symbols": ["NVDA"],
                "rate_limit_per_minute": 60_000,
            },
        },
        official_sources={
            **base.official_sources,
            "sources": [
                {**source, "enabled": False}
                for source in base.official_sources.get("sources", [])
                if isinstance(source, dict)
            ],
        },
        automation={**base.automation, "market_data": {"enabled": False}},
        file_drop={**base.file_drop, "output_dir": str(output_dir)},
    )
    pipeline = NewsIntelligencePipeline(
        config=config,
        repositories=RepositoryBundle(isolated_database),
        clock=lambda: FIXED_NOW,
    )

    def fetch_text(
        _self: EodhdNewsConnector,
        _url: str,
        _headers: dict[str, str],
        _timeout: int,
    ) -> str:
        return json.dumps(
            [
                {
                    "id": "eodhd-2021-nvda-1",
                    "title": "NVIDIA reports earnings above expectations and raises guidance",
                    "date": "2021-03-01T14:00:00+00:00",
                    "link": "https://example.test/nvda-2021",
                    "content": BODY,
                    "symbols": ["NVDA.US"],
                }
            ]
        )

    monkeypatch.setattr(EodhdNewsConnector, "_fetch_text", fetch_text)

    result = IntelligenceRefreshService(pipeline).backfill(
        start=date(2021, 1, 1),
        end=date(2021, 12, 31),
        limit=100,
        page_limit=50,
        max_pages=1,
    )

    assert result["reason"] == "historical_backfill"
    assert result["fetched_count"] == 1
    assert result["ingested_count"] == 1
    assert result["final_record_count"] >= 1
    assert result["export_manifest"]["date_range"] == {
        "from": "2021-01-01",
        "to": "2021-12-31",
    }
    assert (output_dir / f"{result['automation_run_id']}_manifest.json").exists()
    progress = progress_store.get(str(result["automation_run_id"]))
    assert progress is not None
    assert progress["status"] == "complete"


def test_official_feed_connector_parses_rss() -> None:
    config = load_config()
    connector = OfficialFeedConnector(
        config,
        {
            "source_id": "test_feed",
            "source_name": "Central Bank Feed",
            "connector_type": "official_feed_test",
            "source_type": "central_bank",
            "country_or_region": "US",
            "enabled": True,
            "url": "https://example.test/rss",
        },
        fetcher=lambda _url, _headers, _timeout: """
        <rss><channel><item>
          <title>Central bank holds rates steady</title>
          <link>https://example.test/rates</link>
          <pubDate>Fri, 10 Jul 2026 14:00:00 GMT</pubDate>
          <description>Policy makers held rates steady.</description>
          <guid>rates-1</guid>
        </item></channel></rss>
        """,
        clock=lambda: FIXED_NOW,
    )

    record = connector.fetch(set())[0]
    raw = connector.to_raw_news_item(record)

    assert record.source_record_id.startswith("official_feed_test:")
    assert raw.headline == "Central bank holds rates steady"
    assert raw.country == "US"


def _pipeline(database_path: Path) -> NewsIntelligencePipeline:
    base = load_config()
    config = replace(
        base,
        sec_edgar={**base.sec_edgar, "enabled": False},
        eodhd={**base.eodhd, "api_token": "", "news": {"enabled": False}},
        official_sources={
            **base.official_sources,
            "sources": [
                {**source, "enabled": False}
                for source in base.official_sources.get("sources", [])
                if isinstance(source, dict)
            ],
        },
        automation={**base.automation, "market_data": {"enabled": False}},
    )
    return NewsIntelligencePipeline(
        config=config,
        repositories=RepositoryBundle(database_path),
        clock=lambda: FIXED_NOW,
    )


def _bar(symbol: str, timestamp: str, close: float) -> MarketDataBar:
    return MarketDataBar(
        symbol=symbol,
        exchange="NASDAQ",
        interval=MarketDataInterval.DAILY,
        timestamp_utc=datetime.fromisoformat(timestamp),
        open=close,
        high=close + 1,
        low=close - 1,
        close=close,
        adjusted_close=close,
        volume=1_000_000,
        loaded_at=FIXED_NOW,
    )
