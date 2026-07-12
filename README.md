# News Intelligence Module

Deterministic MVP for turning financial news into normalised event JSON, affected instrument impacts, duplicate clusters, and collector-style news signals.

This sprint intentionally excludes live provider integrations, LLM classification, machine learning, broker integration, order execution, position sizing, production authentication, and historical calibration.

## Quick Start

```bash
python -m pip install -e .[dev]
uvicorn news_intelligence.main:app --reload
```

Open `http://127.0.0.1:8000/` for the dashboard.

CLI example:

```bash
news-intelligence --file examples/nvda_earnings.json --no-persist
```

## Architecture

The module is split into replaceable components:

- `models`: public Pydantic contracts and JSON Schema generation.
- `ingestion`: payload coercion from API, CLI, or fixtures.
- `normalisation`: text cleanup, source credibility enrichment, symbol detection, content hashing.
- `classification`: deterministic rule engine backed by `config/event-rules.yaml`.
- `entity_resolution`: instrument and ETF relationship expansion from configuration.
- `clustering`: deterministic duplicate and material-update grouping.
- `scoring`: freshness and instrument impact scoring.
- `collectors`: instrument-specific news signal snapshots.
- `storage`: SQLite JSON repositories behind simple interfaces.
- `api`: FastAPI endpoints and static dashboard hosting.

## Data Flow

```text
Raw News
-> Normalised News
-> Event Classification
-> Entity Resolution
-> Event Cluster
-> Instrument Impacts
-> News Signal
```

The pipeline keeps direction, signed directional strength, confidence, quality, and freshness separate. Scores use the required ranges:

- `directional_strength`: `-1.0` to `1.0`
- `confidence`: `0.0` to `1.0`
- `quality`: `0.0` to `1.0`
- `freshness`: `0.0` to `1.0`

## API

Implemented endpoints:

- `POST /news/analyse`
- `POST /news/events`
- `GET /news/events/recent`
- `GET /news/events/{event_id}`
- `GET /news/events/{event_id}/detail`
- `GET /news/clusters/{cluster_id}`
- `GET /news/signals/{symbol}`
- `POST /test-runs`
- `GET /test-runs`
- `DELETE /test-runs/{test_run_id}`
- `DELETE /development-data`
- `GET /sources/status`
- `GET /schemas`
- `GET /health`
- `GET /`
- `GET /static/...`

`POST /news/analyse` accepts a single raw item, a list of raw items, or an object with an `items` list.

## Event Taxonomy

The public model supports:

`earnings`, `guidance`, `profit_warning`, `corporate_action`, `merger_acquisition`, `contract_commercial`, `product_technology`, `management_governance`, `regulatory_legal`, `analyst_market_view`, `macro_economic`, `central_bank`, `geopolitical`, `commodity_supply`, `sector_industry`, `market_structure`, `etf_fund`, `scheduled_event`, `rumour_unconfirmed`, and `unknown`.

Each event also carries `event_subtype`.

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

Export schemas:

```bash
python -m news_intelligence.schemas.export --output schemas
```

## Adding an Event Rule

1. Edit `config/event-rules.yaml`.
2. Add a unique `id`, `event_type`, `event_subtype`, `event_status`, `direction`, scores, roles, and match terms.
3. Keep broad rules at lower priority than more specific rules.
4. Add `additional_entities` or `impact_overrides` only when the event affects instruments that cannot be inferred from the issuer relationship map.
5. Add or update a fixture in `tests/fixtures/scenarios.json`.
6. Run `python -m pytest -p no:cacheprovider`.

## Adding an Instrument Relationship

1. Edit `config/instrument-relationships.yaml`.
2. Add the direct instrument row first.
3. Add ETF, sector, index, commodity, supplier, customer, or competitor rows with relevance and multiplier values.
4. Keep relationships in configuration, not application logic.
5. Add a scenario covering direct and derived impacts.

## Dashboard

The static dashboard lives in `frontend/` and uses only HTML, CSS, and vanilla JavaScript. It is served by FastAPI at `/`.

Live mode uses:

- `POST /news/analyse`
- `GET /news/events/recent`
- `GET /news/events/{event_id}/detail`
- `GET /sources/status`
- `GET /health`
- `POST /test-runs`
- `GET /test-runs`
- `DELETE /test-runs/{test_run_id}`
- `DELETE /development-data`

Mock mode is controlled by the single frontend flag in `frontend/js/api.js`:

```javascript
const MOCK_MODE = false;
```

For local preference testing, the API wrapper also honours `localStorage.newsIntelligenceMockMode = "true"`.

## Storage

SQLite is used for the MVP. Repositories exist for raw news, normalised news, events, clusters, impacts, and signal snapshots. Payloads are stored as JSON so the repository boundary can later be replaced by PostgreSQL without changing the domain pipeline contracts.

## Known Limitations

- Entity resolution is alias and ticker based.
- Classification is deterministic keyword matching.
- Source credibility is static configuration.
- Freshness uses configured exponential decay but is not calibrated against historical market reaction.
- Price-action integration is a stub represented by metadata or matching rejection text.
- Dashboard mock mode mirrors the backend shape but is not a second authoritative implementation.

## Future Historical Calibration Design

The next calibration increment should store event outcomes with subsequent return windows, volatility regime, liquidity, source type, and surprise proxies. Calibration can then estimate event-type priors, half-life decay curves, impact multipliers, and confidence adjustments by instrument class. The deterministic rule engine should remain as a fallback and as a labelled-data generator for later trained classifiers.
