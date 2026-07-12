# Asterius News Intelligence

Deterministic financial-news intelligence module for turning raw market news into structured events, duplicate-aware event clusters, instrument impacts, and versioned trading-signal snapshots.

This project is an MVP research system. It is designed to make news processing behaviour inspectable and testable before adding live source connectors, LLM classification, broker integration, order execution, or production authentication.

Not financial advice. The generated signals are research artifacts and are not an automated trading system.

## What It Does

- Normalises raw news payloads from the API, CLI, dashboard fixtures, or source adapters.
- Classifies events with deterministic rules from `config/event-rules.yaml`.
- Resolves affected instruments and related ETFs/sectors from `config/instrument-relationships.yaml`.
- Groups articles into event clusters with explicit `NEW_EVENT`, `DUPLICATE`, and `MATERIAL_UPDATE` handling.
- Keeps `article_count`, `duplicate_count`, and `update_count` separate.
- Preserves event versions and signal snapshots when material facts change.
- Scores instrument impact, confidence, quality, freshness, and signal direction separately.
- Adds an explainable `-100` to `+100` news signal score with composition and risk factors.
- Provides a FastAPI backend, SQLite storage, CLI entry point, static dashboard, SEC EDGAR connector, and controlled world-news JSON connector.
- Supports isolated dashboard test runs so fixtures do not aggregate with historical development data.
- Supports a configured favourites universe, automation status, calibration report scaffold, and atomic file-drop JSON export.

## Current Status

Implemented:

- Deterministic event classification and instrument impact generation.
- Duplicate clustering and material-update versioning.
- SQLite JSON persistence.
- Dashboard with event, cluster, evidence, signal, JSON, source, and test panels.
- Left-navigation dashboard shell with Sources, Events, Signals, Favourites, Calibration, File Drop, JSON/Audit, and Developer views.
- Test-run controls for deterministic fixture testing.
- Favourites-universe config for the initial calibration/source-monitoring scope.
- Controlled world-news JSON source family for market-relevant geopolitical and macro events.
- Background-capable scheduler for due/stale source checks, manual automation runs, retry handling, retention housekeeping, and run history.
- Atomic file-drop exporter for cleansed signal/event JSON payloads.
- Calibration report scaffold over persisted favourite-universe signals.
- Unit and integration tests for duplicate handling, material updates, signal snapshots, deletion, reset behaviour, world-news ingestion, signal scoring, file-drop export, and calibration scaffolding.

Intentionally not implemented yet:

- Live licensed world-news provider integration.
- Additional external source connectors beyond SEC EDGAR and the controlled world-news JSON adapter.
- LLM or machine-learning classification.
- Broker/order-management integration.
- Production authentication and multi-user permissions.
- Historical market-data outcome joins and learned calibration parameters.

## Quick Start

Requires Python 3.12 or newer.

```bash
python -m pip install -e .[dev]
python -m uvicorn news_intelligence.main:app --app-dir src --reload
```

Open the dashboard:

```text
http://127.0.0.1:8000/
```

Run the CLI against the example payload:

```bash
news-intelligence --file examples/nvda_earnings.json --no-persist
```

## Dashboard Workflow

The dashboard is served by FastAPI at `/` and uses vanilla HTML, CSS, and JavaScript from `frontend/`.

It is organised as a left-navigation operational console:

- `Overview`: current analysis, pipeline status, recent events, and automation health.
- `Sources`: connector status, due/stale checks, SEC polling, world-news polling, and ingested source records.
- `Events`: recent events, clusters, update/duplicate counts, and event audit trail.
- `Signals`: signal score, confidence, quality, freshness, composition, risk, evidence, and impacts.
- `Favourites`: configured trading/research universe.
- `Calibration`: current historical-calibration report scaffold.
- `File Drop`: configured output directory and latest signal export action.
- `JSON / Audit`: raw contract inspection.
- `Developer`: deterministic fixtures, test-run controls, and reset controls.

The top-right `Options` menu opens less-frequent operational views, including `Sources`, `Developer`, and `Storage / Retention`. The storage view summarises current payload usage by layer, shows the measured days/ticker span, lets retention sliders model projected storage, and provides a dry-run/apply workflow for development/test cleanup.

For deterministic fixture testing:

1. Open the `Developer` view.
2. Click `Start New Test Run`.
3. Load or submit fixture articles.
4. Inspect `Event`, `Cluster`, `Signal`, `Event versions`, and `Signal snapshots`.
5. Use `Delete Current Test Run` to remove only the active test-run records.
6. Use `Reset Development Data` to delete development/test records while preserving production-labelled records.

The active `test_run_id` is displayed in the Test panel. Previous test runs remain listed until they are explicitly deleted or development data is reset.

For SEC ingestion:

1. Open the `Sources` view.
2. Review connector status.
3. Click `Poll SEC EDGAR 8-Ks`.
4. Inspect recent ingested filings.
5. Click a recent event to inspect the classified event, cluster, impacts, and signal JSON.

## Core Data Flow

```text
Raw News
-> Normalised News
-> Event Classification
-> Entity Resolution
-> Event Cluster
-> Instrument Impacts
-> News Signal
```

The pipeline keeps these metrics separate:

- `directional_strength`: `-1.0` to `1.0`
- `confidence`: `0.0` to `1.0`
- `quality`: `0.0` to `1.0`
- `freshness`: `0.0` to `1.0`

## Duplicate And Material Update Handling

Every incoming article is classified at cluster level as one of:

- `NEW_EVENT`: a different underlying event, creating a new cluster.
- `DUPLICATE`: same event with no materially new facts.
- `MATERIAL_UPDATE`: same event with new facts that can change interpretation.

Example:

```text
Article 1: takeover rumour
Article 2: syndicated duplicate
Article 3: company confirmation
```

Expected cluster:

```json
{
  "article_count": 3,
  "duplicate_count": 1,
  "update_count": 1,
  "event_status": "confirmed",
  "signal_snapshot_count": 2
}
```

Duplicate articles increase `article_count` and `duplicate_count` but do not strengthen the active signal. Material updates increase `article_count` and `update_count`, merge new material facts into the canonical event, re-run impact/signal calculation, and preserve previous event/signal versions for audit history.

## Test Run Isolation

Fixture and dashboard testing can attach a `test_run_id` to incoming raw news. When present, clustering only considers records with the same `test_run_id`.

```python
candidate_clusters = clusters.where(test_run_id=incoming.test_run_id)
```

Normal ingestion can leave `test_run_id` as `null` and continue using persistent clustering.

Records also carry:

- `record_environment`: `development`, `test`, or `production`
- `test_run_id`: nullable test-run identifier

`DELETE /development-data` deletes development/test records only. Production-labelled records are retained.

## API

Implemented endpoints:

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/news/analyse` | Analyse raw news and persist the result |
| `POST` | `/news/events` | Alias for analysis flow |
| `GET` | `/news/events/recent` | List recent persisted events |
| `GET` | `/news/events/{event_id}` | Fetch one event |
| `GET` | `/news/events/{event_id}/detail` | Fetch event, cluster, impacts, and signals |
| `GET` | `/news/clusters/{cluster_id}` | Fetch one event cluster |
| `GET` | `/news/signals/{symbol}` | Fetch recent signals for an instrument |
| `GET` | `/universe/favourites` | Fetch the configured favourites universe |
| `POST` | `/test-runs` | Create an isolated dashboard/test run |
| `GET` | `/test-runs` | List historical test runs |
| `DELETE` | `/test-runs/{test_run_id}` | Delete records for one test run |
| `DELETE` | `/development-data` | Delete development/test records only |
| `POST` | `/sources/sec-edgar/poll` | Poll configured SEC EDGAR companies for new 8-K filings |
| `POST` | `/sources/world-news/poll` | Poll configured world-news JSON records |
| `POST` | `/sources/poll-due` | Poll connectors that are due, or force all connectors |
| `GET` | `/sources/filings/recent` | List recently ingested source filings |
| `GET` | `/sources/items/recent` | List recently ingested source records |
| `GET` | `/sources/status` | Show configured source status |
| `GET` | `/automation/status` | Show due/stale source state, background runner state, and recent automation runs |
| `POST` | `/automation/run-now` | Run due-source polling and configured retention housekeeping immediately |
| `GET` | `/calibration/report` | Build the current calibration profile report |
| `GET` | `/calibration/outcomes` | Join persisted news signals to cached market data and calculate forward returns |
| `POST` | `/market-data/eodhd/fetch` | Fetch and cache bounded EODHD daily or intraday bars |
| `GET` | `/market-data/bars/recent` | List recently cached market-data bars |
| `GET` | `/market-data/requests/recent` | List recent market-data request audit records |
| `GET` | `/outputs/file-drop/status` | Show file-drop output configuration |
| `POST` | `/outputs/file-drop/signals/{signal_id}` | Export one signal payload to file drop |
| `POST` | `/outputs/file-drop/latest` | Export recent signal payloads to file drop |
| `GET` | `/storage/layers` | Summarise storage by layer and retention profile |
| `POST` | `/storage/retention/dry-run` | Preview eligible retention cleanup by layer |
| `POST` | `/storage/retention/apply` | Apply retention cleanup to eligible development/test records |
| `GET` | `/schemas` | Export public JSON Schemas |
| `GET` | `/health` | Health check |
| `GET` | `/` | Dashboard |
| `GET` | `/static/...` | Dashboard static assets |

`POST /news/analyse` accepts a single raw item, a list of raw items, or an object with an `items` list.

Example request:

```json
{
  "headline": "Apple confirms preliminary takeover approach",
  "body": "Company A confirms that it has received a preliminary takeover approach.",
  "source_name": "Company Press Release",
  "source_type": "company",
  "published_at": "2026-07-11T10:30:00Z",
  "known_ticker": "AAPL",
  "source_article_id": "example-001",
  "test_run_id": "test_run_example",
  "record_environment": "test"
}
```

## Architecture

The code is split into replaceable modules:

- `models`: Pydantic contracts and JSON Schema generation.
- `ingestion`: API/CLI/fixture payload coercion.
- `normalisation`: text cleanup, source enrichment, symbol detection, content hashing.
- `classification`: deterministic rule engine.
- `entity_resolution`: issuer, ETF, sector, and related-instrument expansion.
- `clustering`: duplicate/material-update grouping and audit trail.
- `scoring`: freshness and instrument impact scoring.
- `collectors`: instrument-specific signal snapshots.
- `calibration`: historical calibration report scaffolding.
- `outputs`: downstream output adapters such as file-drop JSON.
- `storage`: SQLite-backed JSON repositories.
- `api`: FastAPI routes and dashboard hosting.

Design notes:

- [Architecture](docs/architecture.md)
- [Source Adapter Guide](docs/source-adapters.md)
- [SEC EDGAR Ingestion](docs/sec-edgar-ingestion.md)
- [Historical Calibration Design](docs/historical-calibration.md)
- [File-Drop Integration Contract](docs/file-drop-integration.md)
- [Manual Frontend Checklist](docs/manual-frontend-checklist.md)

## Project Layout

```text
config/                         Rule, source, freshness, runtime, automation, file-drop, and universe config
docs/                           Design docs, source notes, and manual QA notes
examples/                       Example raw news payloads
frontend/                       Static dashboard
src/news_intelligence/          Application package
tests/                          Unit, integration, and fixture tests
```

## Configuration

Runtime environment is configured in `config/runtime.yaml`:

```yaml
environment: development
```

It can also be overridden with:

```bash
NEWS_INTELLIGENCE_ENVIRONMENT=test
```

Valid values:

- `development`
- `test`
- `production`

Fixture-generated records should be stored as `test` or `development`, never `production`.

SEC EDGAR ingestion is configured in `config/sec-edgar.yaml`. The first connector is intentionally restricted to:

```text
NVDA, AMD, AAPL, XOM, JPM, MRNA, BA
```

The connector currently polls 8-K filings only. It captures CIK, accession number, company, form type, filing time, filing URL, primary document URL, and filing sections before converting the filing into `RawNewsItem`.

SEC requests use an identifying User-Agent from config:

```yaml
user_agent: Asterius News Intelligence street.nic@gmail.com
```

Override it without editing config:

```bash
SEC_EDGAR_USER_AGENT="Your App Name your.email@example.com"
```

The connector rate-limits requests below SEC's published max request rate, retries transient failures, and skips filings whose accession number has already been stored.

Dashboard polling inspects the newest configured 8-K window for each company. It does not keep walking backward to backfill older filings after the newest records are already known.

EODHD market-data settings live in `config/eodhd.yaml`. The tracked file must not contain the API key. Use either an environment variable:

```bash
EODHD_API_TOKEN="your-token"
```

or copy the committed example file:

```text
config/eodhd.local.example.yaml -> config/eodhd.local.yaml
```

and put the token in `config/eodhd.local.yaml`. The `config/*.local.yaml` pattern is ignored by Git, so local secret config stays out of commits.

EODHD is used as a market-data adapter for historical calibration, not as a news source. It can cache:

- daily OHLCV/adjusted-close bars
- selected intraday bars around event windows
- request audit records with estimated API call cost

Example bounded fetch:

```json
{
  "symbol": "AAPL",
  "exchange": "NASDAQ",
  "interval": "1d",
  "from": "2026-07-01",
  "to": "2026-07-12"
}
```

The API token is never returned in market-data request records.

The favourites universe is configured in `config/favourites.yaml`. It currently includes the US shares, ETFs, indices, and UK LSE GBP ETFs listed for the initial calibration scope.

World-news ingestion is configured in `config/world-news.yaml`. The current adapter is a controlled JSON source for market-relevant geopolitical and macro records covering the US, UK, China, Europe, and global-market risk themes.

Automation and file-drop output are configured in:

```text
config/automation.yaml
config/file-drop.yaml
```

Automation is explicit and inspectable through `/automation/status`, `/automation/run-now`, and `/sources/poll-due`.

`config/automation.yaml` controls:

- whether the background runner starts automatically
- startup polling
- scheduler interval
- source stale thresholds
- optional retention housekeeping

The dashboard Automation panel shows background runner state, due/stale source status, last/next poll times, source failures, and recent automation run history. Automation is disabled by default until `automation.enabled` is set to `true`.

File-drop export writes completed `.json` files through an atomic `.tmp` rename.

## Tests And Validation

Run the full test suite:

```bash
python -m pytest
```

Run linting:

```bash
python -m ruff check .
```

Run static type checks:

```bash
python -m mypy src tests
```

Current validation state at the time this README was written:

```text
python -m pytest        34 passed, 1 skipped
python -m ruff check .  passed
python -m mypy src tests passed
```

The live SEC integration test is opt-in:

```bash
NEWS_INTELLIGENCE_LIVE_SEC=1 SEC_EDGAR_USER_AGENT="Your App Name email@example.com" python -m pytest tests/integration/test_sec_edgar_live.py
```

## JSON Contracts

Public contracts are Pydantic models:

- `RawNewsItem`
- `NormalisedNewsItem`
- `NewsSource`
- `FavouritesUniverse`
- `ResolvedEntity`
- `NewsEvent`
- `NewsEventCluster`
- `InstrumentNewsImpact`
- `NewsSignal`
- `SourceIngestedItem`
- `SourceIngestedFiling`
- `SourceConnectorStatus`
- `SourceIngestionRun`
- `ProcessingLineage`
- `NewsAnalysisResult`

Export JSON Schemas:

```bash
python -m news_intelligence.schemas.export --output schemas
```

## Event Taxonomy

Supported event types include:

```text
earnings
guidance
profit_warning
corporate_action
merger_acquisition
contract_commercial
product_technology
management_governance
regulatory_legal
analyst_market_view
macro_economic
central_bank
geopolitical
commodity_supply
sector_industry
market_structure
etf_fund
scheduled_event
rumour_unconfirmed
unknown
```

Each event also carries an `event_subtype`.

## Storage

SQLite is used for the MVP. Repositories store JSON payloads for:

- raw news
- normalised news
- events
- event clusters
- instrument impacts
- signal snapshots
- source lineage records
- market-data request audit records
- event outcomes
- calibration profiles
- file-drop JSON outputs

Market bars use a structured SQLite table keyed by `symbol`, `exchange`, `interval`, and `timestamp_utc` so calibration can do deterministic range queries without scanning large JSON payloads.

Generated SQLite databases are ignored by Git. The repository boundary is intentionally simple so SQLite can later be replaced by PostgreSQL without changing the domain contracts.

Storage-retention defaults live in `config/retention.yaml`. `GET /storage/layers` reports logical JSON payload bytes, record count, ticker count, days worth of retained data, estimated bytes per day, and projected storage for adjustable layers.

Market-data retention is split into:

- `market_daily_bars`
- `market_intraday_bars`
- `market_data_requests`
- `event_outcomes`
- `calibration_profiles`

Daily and intraday bars are adjustable cache layers. Event outcomes and calibration profiles are retained as versioned research/audit data.

Retention enforcement is explicit:

- `POST /storage/retention/dry-run` previews eligible records/files by layer.
- `POST /storage/retention/apply` deletes only eligible development/test/unlabelled records and configured file-drop JSON.
- Production-labelled records are always skipped.
- Canonical events, clusters, source lineage, and calibration layers remain audit/permanent layers in the current policy.

## Adding An Event Rule

1. Edit `config/event-rules.yaml`.
2. Add a unique `id`, event type/subtype/status, direction, scores, roles, and match terms.
3. Keep broad rules at lower priority than specific rules.
4. Add `additional_entities` or `impact_overrides` only when instrument impact cannot be inferred from the relationship map.
5. Add or update a fixture in `tests/fixtures/scenarios.json`.
6. Run `python -m pytest`.

## Adding An Instrument Relationship

1. Edit `config/instrument-relationships.yaml`.
2. Add the direct instrument row first.
3. Add ETF, sector, index, commodity, supplier, customer, or competitor rows with relevance and multiplier values.
4. Keep relationship logic in configuration rather than code where practical.
5. Add a scenario covering direct and derived impacts.

## Roadmap

Delivery milestones:

| Version | Milestone |
| --- | --- |
| `v0.1` | Deterministic fixture-driven MVP |
| `v0.2` | First live authoritative source |
| `v0.3` | Multi-source ingestion and monitoring |
| `v0.4` | Historical event calibration |
| `v0.5` | Strategy and indicator-aggregator integration |
| `v1.0` | Validated production-ready news intelligence service |

Current source adapter pattern:

```text
Source adapter interface
-> SEC EDGAR connector
-> raw item ingestion
-> source lineage preservation
-> existing pipeline pass-through
-> dashboard display
```

Likely source sequence:

1. UK RNS or company investor-relations feeds
2. Japan TDnet
3. Macro release feeds
4. Licensed global news provider

Later platform increments:

- Explicit `Backfill SEC History` workflow with date range, company selection, form filters, per-company limits, dry-run preview, and clear separation from operational polling.
- File-drop output adapter for cleansed signal JSON into a trading-app ingest directory.
- Dashboard UI rework into a more logical operating view:
  - source ingestion and filing queue
  - events and clusters
  - active signal details
  - audit/history JSON
  - developer/test controls
- Source-to-event drilldown so an ingested filing can be opened directly into its event, cluster, impacts, and signal snapshots.
- Filtering and search for filings, events, clusters, symbols, forms, source, environment, and test run.
- Better empty/loading/error states for long-running ingestion and source failures.
- Historical outcome calibration.
- Better source credibility modelling.
- Configurable persistence backend.
- Authentication and production deployment controls.
- Optional LLM-assisted classification behind deterministic fallbacks.

## Development Notes

- Keep generated files out of Git: SQLite databases, caches, logs, and local test data are ignored.
- Preserve deterministic tests for every new event rule and source connector.
- Treat source adapters as provenance-preserving ingestion layers. They should produce raw news items and let the existing pipeline handle classification, clustering, scoring, and signal generation.
