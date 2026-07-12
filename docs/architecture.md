# Architecture

Asterius News Intelligence is built as a deterministic news-to-signal pipeline. The current system is intentionally modular: source adapters collect raw facts, the core pipeline classifies and scores them, and output contracts remain stable for downstream consumers.

## Goals

- Preserve source lineage from ingestion through final signal JSON.
- Keep deterministic behaviour testable with fixtures.
- Separate source-specific parsing from event classification and signal generation.
- Keep duplicate articles, material updates, and separate events distinct.
- Produce structured JSON that a trading system can consume without scraping dashboard state.

## Non-Goals

- No order execution.
- No broker integration.
- No discretionary trade recommendation.
- No live LLM dependency in the core path.
- No production auth or multi-user permission model yet.

## System Shape

```text
External source
-> SourceAdapter
-> SourceIngestionService
-> RawNewsItem
-> NewsIntelligencePipeline
-> NewsAnalysisResult
-> SQLite repositories
-> API/dashboard
-> file-drop JSON exporter
-> trading application
```

## Main Components

### Source Adapters

Source adapters live under `src/news_intelligence/sources/`.

They are responsible for:

- connecting to an external source
- respecting source rate limits and retry rules
- preserving source-specific identifiers and lineage
- converting source records into `RawNewsItem`

They are not responsible for:

- event classification
- instrument impact scoring
- signal generation
- trading decisions

### Ingestion Service

`SourceIngestionService` wraps adapters and handles source-level persistence.

Responsibilities:

- check already ingested source record IDs
- skip duplicate accessions or source IDs
- persist `SourceIngestedFiling`
- run new items through `NewsIntelligencePipeline`
- update `SourceConnectorStatus`

### Pipeline

`NewsIntelligencePipeline` is the deterministic core.

```text
Raw News
-> Normalised News
-> Event Classification
-> Entity Resolution
-> Event Cluster
-> Instrument Impacts
-> News Signal
```

Each stage emits a typed Pydantic contract. These contracts make the pipeline inspectable in tests, API responses, and the dashboard.

### Storage

SQLite is used for the MVP. The storage layer is deliberately thin: each repository stores JSON payloads by stable ID.

Current repositories:

- `raw_news`
- `normalised_news`
- `events`
- `event_clusters`
- `instrument_impacts`
- `signal_snapshots`
- `source_filings`
- `source_status`

Generic non-filing source records are stored through the same source-record repository in this MVP. SEC-specific filing fields remain available on SEC records.

This boundary is intended to be replaceable later with PostgreSQL or a message/event store.

### API And Dashboard

FastAPI exposes analysis, source ingestion, status, schema, and dashboard endpoints. The dashboard is an inspection and test surface, not the integration contract for the trading application.

The future trading integration should consume cleansed JSON files written to a configured directory, not scrape dashboard state.

## Core Contracts

The most important contracts are:

- `RawNewsItem`
- `NormalisedNewsItem`
- `NewsEvent`
- `NewsEventCluster`
- `InstrumentNewsImpact`
- `NewsSignal`
- `SourceIngestedFiling`
- `SourceConnectorStatus`
- `NewsAnalysisResult`

Schemas can be exported with:

```bash
python -m news_intelligence.schemas.export --output schemas
```

## Event And Signal Versioning

Clusters preserve history:

- `articles`: every article attached to the cluster
- `event_versions`: canonical event state over time
- `signal_snapshots`: signal versions over time

The latest signal snapshot is active. Previous snapshots remain queryable for audit.

## Duplicate And Material Update Rules

Each incoming item is classified as:

- `NEW_EVENT`
- `DUPLICATE`
- `MATERIAL_UPDATE`

Duplicates increase article and duplicate counts but do not strengthen signals. Material updates create new event/signal versions and trigger recalculation.

## Runtime Environments

Records carry:

- `record_environment`: `development`, `test`, or `production`
- `test_run_id`: optional isolated test-run identifier

Fixture and dashboard test runs should not match production clusters.

## File-Drop Integration Direction

The planned trading-app integration is intentionally simple:

```text
News pipeline
-> cleansed signal JSON
-> atomic file write to output directory
-> trading app ingests file
-> trading app owns strategy/risk decisions
```

This keeps the news service independent from trading-process lifecycle and allows the ingestion model in the trading app to be rebuilt around a clean JSON contract.
