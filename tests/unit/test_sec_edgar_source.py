from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from news_intelligence.config import NewsIntelligenceConfig, load_config
from news_intelligence.pipeline import NewsIntelligencePipeline
from news_intelligence.sources.sec_edgar import SecEdgarConnector
from news_intelligence.sources.service import SourceIngestionService
from news_intelligence.storage import RepositoryBundle

FIXED_NOW = datetime(2026, 7, 12, 12, 0, tzinfo=UTC)


def test_sec_edgar_connector_converts_8k_to_raw_news() -> None:
    connector = SecEdgarConnector(_sec_config(), fetcher=_fake_sec_fetcher, clock=lambda: FIXED_NOW)

    filings = connector.fetch()
    raw_item = connector.to_raw_news_item(filings[0])

    assert len(filings) == 1
    assert filings[0].cik == "0001045810"
    assert filings[0].accession_number == "0001045810-26-000123"
    assert filings[0].company == "NVIDIA CORP"
    assert filings[0].form_type == "8-K"
    assert filings[0].filing_sections == ["2.02", "9.01"]
    assert "Archives/edgar/data/1045810/000104581026000123" in filings[0].filing_url
    assert raw_item.known_ticker == "NVDA"
    assert raw_item.source_article_id == "0001045810-26-000123"
    assert raw_item.source.source_name == "SEC EDGAR"
    assert raw_item.metadata["cik"] == "0001045810"
    assert "earnings above expectations" in (raw_item.body or "")


def test_sec_edgar_ingestion_stores_once_and_runs_pipeline(isolated_database: Path) -> None:
    pipeline = NewsIntelligencePipeline(
        config=_sec_config(),
        repositories=RepositoryBundle(isolated_database),
        clock=lambda: FIXED_NOW,
    )
    service = SourceIngestionService(pipeline)
    connector = SecEdgarConnector(
        pipeline.config,
        fetcher=_fake_sec_fetcher,
        clock=lambda: FIXED_NOW,
    )

    first = service.ingest(connector, force=True)
    second = service.ingest(connector, force=True)

    assert first.fetched_count == 1
    assert first.ingested_count == 1
    assert first.error_count == 0
    assert second.fetched_count == 0
    assert second.ingested_count == 0
    assert len(pipeline.repositories.source_filings.list_all()) == 1
    assert len(pipeline.repositories.raw_news.list_all()) == 1

    stored_filing = pipeline.repositories.source_filings.list_all()[0]
    assert stored_filing["accession_number"] == "0001045810-26-000123"
    assert stored_filing["event_id"]
    assert stored_filing["cluster_id"]

    events = pipeline.repositories.events.list_all()
    assert events[0]["event_type"] == "earnings"
    assert events[0]["event_subtype"] == "beat_and_raise"
    impacts = pipeline.repositories.impacts.list_all()
    assert {"NVDA", "SMH"}.issubset({impact["symbol"] for impact in impacts})
    signals = pipeline.repositories.signals.list_all()
    assert any(signal["instrument"]["symbol"] == "NVDA" for signal in signals)


def test_sec_edgar_repeat_poll_does_not_backfill_older_8ks(isolated_database: Path) -> None:
    pipeline = NewsIntelligencePipeline(
        config=_sec_config(max_filings_per_company=1),
        repositories=RepositoryBundle(isolated_database),
        clock=lambda: FIXED_NOW,
    )
    service = SourceIngestionService(pipeline)
    connector = SecEdgarConnector(
        pipeline.config,
        fetcher=_fake_sec_fetcher,
        clock=lambda: FIXED_NOW,
    )

    first = service.ingest(connector, force=True)
    second = service.ingest(connector, force=True)

    assert first.ingested_count == 1
    assert second.fetched_count == 0
    assert second.ingested_count == 0
    assert {
        filing["accession_number"]
        for filing in pipeline.repositories.source_filings.list_all()
    } == {"0001045810-26-000123"}


def _sec_config(*, max_filings_per_company: int = 1) -> NewsIntelligenceConfig:
    base = load_config()
    sec_edgar = {
        **base.sec_edgar,
        "enabled": True,
        "max_filings_per_company": max_filings_per_company,
        "companies": [
            {
                "symbol": "NVDA",
                "cik": "0001045810",
                "company": "NVIDIA CORP",
            }
        ],
    }
    return NewsIntelligenceConfig(
        root=base.root,
        event_rules=base.event_rules,
        instrument_relationships=base.instrument_relationships,
        source_credibility=base.source_credibility,
        freshness_half_lives=base.freshness_half_lives,
        runtime=base.runtime,
        sec_edgar=sec_edgar,
    )


def _fake_sec_fetcher(url: str, _headers: dict[str, str], _timeout: int) -> str:
    if url.endswith("/submissions/CIK0001045810.json"):
        return json.dumps(_submission_fixture())
    if url.endswith("/nvda-20260630x8k.htm"):
        return """
        <html>
          <body>
            <h1>FORM 8-K CURRENT REPORT</h1>
            <p>Item 2.02 Results of Operations and Financial Condition.</p>
            <p>NVIDIA reports earnings above expectations and raises guidance.</p>
            <p>Item 9.01 Financial Statements and Exhibits.</p>
          </body>
        </html>
        """
    raise AssertionError(f"Unexpected SEC fixture URL: {url}")


def _submission_fixture() -> dict[str, Any]:
    return {
        "cik": "0001045810",
        "name": "NVIDIA CORP",
        "filings": {
            "recent": {
                "accessionNumber": [
                    "0001045810-26-000123",
                    "0001045810-26-000100",
                    "0001045810-26-000099",
                ],
                "form": ["8-K", "10-Q", "8-K"],
                "acceptanceDateTime": [
                    "2026-06-30T16:30:35.000Z",
                    "2026-06-01T16:30:35.000Z",
                    "2026-05-30T16:30:35.000Z",
                ],
                "filingDate": ["2026-06-30", "2026-06-01", "2026-05-30"],
                "primaryDocument": [
                    "nvda-20260630x8k.htm",
                    "nvda-20260601x10q.htm",
                    "nvda-20260530x8k.htm",
                ],
                "items": ["2.02,9.01", "", "8.01"],
            }
        },
    }
