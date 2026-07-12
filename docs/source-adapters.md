# Source Adapter Guide

Source adapters convert external feeds into the internal `RawNewsItem` contract while preserving source lineage.

## Current Adapter

Implemented:

- `SEC EDGAR`
- configured US shares: `NVDA`, `AMD`, `AAPL`, `XOM`, `JPM`, `MRNA`, `BA`
- form scope: `8-K`
- `World News Monitor`
- controlled JSON source for market-relevant geopolitical and macro records
- first scope: US, UK, China, Europe, and global-market risk themes

Planned:

- UK RNS or company investor-relations feeds
- Japan TDnet
- macro release feeds
- licensed global news provider

## Adapter Interface

Adapters implement the protocol in `src/news_intelligence/sources/base.py`:

```python
class SourceAdapter(Protocol):
    adapter_id: str
    source_name: str
    connector_type: str
    enabled: bool
    poll_interval: timedelta

    def fetch(
        self,
        known_source_record_ids: set[str] | None = None,
    ) -> Sequence[SourceIngestedFiling]:
        ...

    def to_raw_news_item(self, filing: SourceIngestedFiling) -> RawNewsItem:
        ...
```

The interface is deliberately small. Source-specific complexity should stay inside the adapter.

The service now supports generic `SourceIngestedItem` records as well as SEC-specific `SourceIngestedFiling` records. SEC filing fields remain available for the filing dashboard, while non-filing feeds can preserve source lineage without pretending to be filings.

## Adapter Responsibilities

An adapter should:

- identify configured source instruments/entities
- fetch source records
- enforce provider rate limits and retry rules
- capture source-native identifiers
- preserve source URLs and timestamps
- parse enough text to classify the event
- emit `SourceIngestedFiling` or a future equivalent source record
- convert source records into `RawNewsItem`

An adapter should not:

- classify the event directly
- calculate instrument impact
- generate trading signals
- write strategy outputs
- silently discard source identifiers

## Source Identity

Every source record needs a stable dedupe key.

For SEC EDGAR:

```text
sec_edgar:{accession_number}
```

For future sources, use the provider-native immutable ID where available. If there is no stable provider ID, derive one from:

- source name
- URL
- publication timestamp
- headline/title
- primary entity

## RawNewsItem Mapping

Adapters should populate:

- `headline`
- `body`
- `source`
- `published_at`
- `source_article_id`
- `tickers`
- `known_ticker`
- `country`
- `market`
- `metadata`

Provider-specific facts should go into `metadata`, for example:

- accession number
- filing sections
- CIK
- original source URL
- primary document URL
- source connector name

## SourceIngestedFiling

The current source record contract is filing-oriented because SEC EDGAR is the first connector.

For non-filing sources, the project may later add a more generic `SourceIngestedItem` contract. Until then, either reuse the existing fields where appropriate or add a parallel source record model rather than forcing unrelated sources into filing semantics.

## Polling Versus Backfill

Operational polling should be latest-window only:

- fetch the newest relevant records
- skip known source IDs
- do not walk backward to fill quotas

Historical backfill should be a separate workflow:

- explicit date range
- source/company selection
- form or item filters
- per-company limits
- dry-run preview
- clear status and cancellation semantics

This separation prevents a manual poll from unexpectedly ingesting historical batches.

## Error Handling

Adapters should report failures through `SourceConnectorStatus`:

- `OK`
- `DEGRADED`
- `DISABLED`
- `ERROR`

Transient external failures should not corrupt existing records. If a source fetch fails, keep prior successful records and surface the failure in connector status.

## Adding A New Adapter

1. Add config under `config/`.
2. Add a source credibility entry in `config/source-credibility.yaml`.
3. Implement adapter under `src/news_intelligence/sources/`.
4. Convert provider records into `RawNewsItem`.
5. Add repository/API/dashboard support only if new source status fields are needed.
6. Add deterministic fixture tests.
7. Add an opt-in live integration test guarded by an environment variable.
8. Document provider constraints, IDs, rate limits, and test commands.

## Acceptance Criteria

A new source adapter is acceptable when:

- it can fetch a controlled source fixture
- it deduplicates source records
- it preserves source lineage
- it produces valid `RawNewsItem`
- the existing pipeline produces an event, cluster, impacts, and signal
- source status is visible in the dashboard/API
- repeat polling does not create duplicates or unexpected backfill

Current implemented endpoints:

- `POST /sources/sec-edgar/poll`
- `POST /sources/world-news/poll`
- `POST /sources/poll-due`
- `GET /sources/status`
- `GET /automation/status`
