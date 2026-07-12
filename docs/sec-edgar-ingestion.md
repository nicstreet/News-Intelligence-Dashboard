# SEC EDGAR Ingestion

This document captures the v0.2 source adapter behaviour.

## Scope

The first real connector is restricted to SEC EDGAR 8-K filings for configured US shares:

```text
NVDA, AMD, AAPL, XOM, JPM, MRNA, BA
```

The connector does not yet ingest 10-Q, 10-K, proxy statements, ownership filings, non-US sources, or licensed news.

## SEC Endpoints

The connector uses the SEC submissions API:

```text
https://data.sec.gov/submissions/CIK##########.json
```

The API returns each company's recent filing history, including form type, accession number, acceptance time, primary document, and 8-K item codes. Primary filing documents are retrieved from the SEC archives path:

```text
https://www.sec.gov/Archives/edgar/data/{cik}/{accession_without_dashes}/{primary_document}
```

SEC reference pages:

- https://www.sec.gov/search-filings/edgar-application-programming-interfaces
- https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data

## Fair Access Controls

The connector includes:

- identifying `User-Agent`
- request rate limiting
- retry handling for transient errors and rate-limit responses
- configurable timeout and retry count
- polling interval enforcement

Configuration lives in `config/sec-edgar.yaml`. The User-Agent can be overridden with `SEC_EDGAR_USER_AGENT`.

## Deduplication

Each SEC filing is keyed by:

```text
sec_edgar:{accession_number}
```

Before a filing is converted into `RawNewsItem`, the ingestion service checks `source_filings`. If the accession has already been stored, the filing is skipped and the pipeline is not re-run.

## Pipeline Flow

```text
SEC submissions JSON
-> filter configured companies and 8-K forms
-> fetch primary filing document
-> capture filing metadata and sections
-> store source filing once
-> convert to RawNewsItem
-> normalisation
-> event classification
-> entity and ETF resolution
-> clustering
-> impact calculation
-> signal snapshot generation
```

## Dashboard

The `Sources` tab shows:

- connector status
- manual `Poll SEC EDGAR 8-Ks` action
- recently ingested filings
- SEC accession links
- associated event IDs

## Tests

Deterministic fixture coverage:

```bash
python -m pytest tests/unit/test_sec_edgar_source.py
```

Opt-in live SEC coverage:

```bash
NEWS_INTELLIGENCE_LIVE_SEC=1 SEC_EDGAR_USER_AGENT="Asterius News Intelligence email@example.com" python -m pytest tests/integration/test_sec_edgar_live.py
```
