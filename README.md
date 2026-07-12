# News Intelligence

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
- Provides a FastAPI backend, SQLite storage, CLI entry point, static dashboard, and SEC EDGAR ingestion connector.
- Supports isolated dashboard test runs so fixtures do not aggregate with historical development data.

## Current Status

Implemented:

- Deterministic event classification and instrument impact generation.
- Duplicate clustering and material-update versioning.
- SQLite JSON persistence.
- Dashboard with event, cluster, evidence, signal, JSON, source, and test panels.
- Test-run controls for deterministic fixture testing.
- Unit and integration tests for duplicate handling, material updates, signal snapshots, deletion, and reset behaviour.

Intentionally not implemented yet:

- Additional external news/source connectors beyond SEC EDGAR.
- LLM or machine-learning classification.
- Broker/order-management integration.
- Production authentication and multi-user permissions.
- Historical outcome calibration.

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

For deterministic fixture testing:

1. Open the `Test` tab.
2. Click `Start New Test Run`.
3. Load or submit fixture articles.
4. Inspect `Event`, `Cluster`, `Signal`, `Event versions`, and `Signal snapshots`.
5. Use `Delete Current Test Run` to remove only the active test-run records.
6. Use `Reset Development Data` to delete development/test records while preserving production-labelled records.

The active `test_run_id` is displayed in the Test panel. Previous test runs remain listed until they are explicitly deleted or development data is reset.

For SEC ingestion:

1. Open the `Sources` tab.
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
| `POST` | `/test-runs` | Create an isolated dashboard/test run |
| `GET` | `/test-runs` | List historical test runs |
| `DELETE` | `/test-runs/{test_run_id}` | Delete records for one test run |
| `DELETE` | `/development-data` | Delete development/test records only |
| `POST` | `/sources/sec-edgar/poll` | Poll configured SEC EDGAR companies for new 8-K filings |
| `GET` | `/sources/filings/recent` | List recently ingested source filings |
| `GET` | `/sources/status` | Show configured source status |
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
- `storage`: SQLite-backed JSON repositories.
- `api`: FastAPI routes and dashboard hosting.

## Project Layout

```text
config/                         Rule, source, freshness, runtime, and instrument config
docs/                           Manual QA notes
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
user_agent: News Intelligence Dashboard street.nic@gmail.com
```

Override it without editing config:

```bash
SEC_EDGAR_USER_AGENT="Your App Name your.email@example.com"
```

The connector rate-limits requests below SEC's published max request rate, retries transient failures, and skips filings whose accession number has already been stored.

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
python -m pytest        28 passed, 1 skipped
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
- `ResolvedEntity`
- `NewsEvent`
- `NewsEventCluster`
- `InstrumentNewsImpact`
- `NewsSignal`
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

Generated SQLite databases are ignored by Git. The repository boundary is intentionally simple so SQLite can later be replaced by PostgreSQL without changing the domain contracts.

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

- Historical outcome calibration.
- Better source credibility modelling.
- Configurable persistence backend.
- Authentication and production deployment controls.
- Optional LLM-assisted classification behind deterministic fallbacks.

## Development Notes

- Keep generated files out of Git: SQLite databases, caches, logs, and local test data are ignored.
- Preserve deterministic tests for every new event rule and source connector.
- Treat source adapters as provenance-preserving ingestion layers. They should produce raw news items and let the existing pipeline handle classification, clustering, scoring, and signal generation.
