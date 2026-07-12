from __future__ import annotations

import os

import pytest

from news_intelligence.config import NewsIntelligenceConfig, load_config
from news_intelligence.sources.sec_edgar import SecEdgarConnector


@pytest.mark.skipif(
    os.environ.get("NEWS_INTELLIGENCE_LIVE_SEC") != "1",
    reason="Set NEWS_INTELLIGENCE_LIVE_SEC=1 to run the controlled SEC EDGAR live test.",
)
def test_live_sec_edgar_fetches_one_configured_8k() -> None:
    base = load_config()
    config = NewsIntelligenceConfig(
        root=base.root,
        event_rules=base.event_rules,
        instrument_relationships=base.instrument_relationships,
        source_credibility=base.source_credibility,
        freshness_half_lives=base.freshness_half_lives,
        runtime=base.runtime,
        sec_edgar={
            **base.sec_edgar,
            "max_filings_per_company": 1,
            "companies": [
                {
                    "symbol": "AAPL",
                    "cik": "0000320193",
                    "company": "APPLE INC",
                }
            ],
        },
    )

    connector = SecEdgarConnector(config)
    filings = connector.fetch()

    assert filings
    assert filings[0].ticker == "AAPL"
    assert filings[0].form_type == "8-K"
    assert filings[0].cik == "0000320193"
    assert filings[0].accession_number
    assert filings[0].filing_url.startswith("https://www.sec.gov/Archives/edgar/data/")
    assert filings[0].primary_document_url.startswith("https://www.sec.gov/Archives/edgar/data/")
