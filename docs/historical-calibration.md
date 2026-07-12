# Historical Calibration Design

Historical calibration is planned for `v0.4`. The goal is to measure how event types, source quality, surprise, confirmation status, and affected instruments relate to subsequent market behaviour.

Current implementation status: the project now has a favourites-universe scoped calibration report at `GET /calibration/report` and a joined outcome view at `GET /calibration/outcomes`. The joined view links persisted news signals to cached market bars, calculates forward returns, benchmark returns, abnormal returns, event anchors, release sessions and missing-data diagnostics. It does not yet update live scoring automatically.

Current market-data foundation:

- EODHD config is loaded from `config/eodhd.yaml` with local secrets kept in ignored `config/eodhd.local.yaml`.
- `MarketDataService` can fetch bounded daily or intraday bars through EODHD.
- `market_bars` stores bars by `symbol`, `exchange`, `interval`, and `timestamp_utc`.
- `market_data_requests` stores request audit records without returning the API token.
- storage retention now manages daily bars, intraday bars and request audits separately.
- `EventMarketTimer` classifies event timing and provides first-tradable-anchor timestamps.
- `JoinedOutcomeAnalysisService` builds the read-only news-vs-market outcome rows used by the dashboard calibration view.

## Purpose

Current scoring is deterministic and rule-based. Calibration should turn observed outcomes into better priors and thresholds while preserving the deterministic pipeline as the explainable baseline.

Calibration should answer:

- Which event types actually move which instruments?
- Over what time horizons?
- How quickly does the impact decay?
- Which sources add signal and which mostly add duplicates?
- Which event fields predict reversals, confirmations, or no reaction?
- Which signal confidence thresholds are useful for downstream strategies?

## Non-Goals

Calibration should not:

- place trades
- optimise a full strategy
- rewrite raw historical facts
- hide deterministic rule decisions
- replace audit trails with opaque model output

## Data To Capture

For each event/signal snapshot, store:

- event ID
- cluster ID
- signal ID and version
- instrument symbol
- event type/subtype
- event status
- direction
- directional strength
- confidence
- quality
- surprise
- novelty
- expected persistence
- source name/type/credibility
- primary source present
- article count
- duplicate count
- update count
- event timestamp
- signal generation timestamp
- affected instrument relationship
- related ETF/sector/index mappings

For market outcomes, store:

- pre-event price
- post-event return windows
- post-event volatility
- volume/liquidity regime
- market/index return over same windows
- sector/ETF return over same windows
- spread/slippage proxy where available
- halt or illiquidity flags

Suggested windows:

```text
5m, 15m, 30m, 1h, 4h, 1d, 3d, 5d, 20d
```

The exact windows should match the downstream trading system's timeframes.

## Outcome Metrics

For each signal:

- raw forward return
- market-adjusted forward return
- sector-adjusted forward return
- max favourable excursion
- max adverse excursion
- realised volatility
- hit rate by threshold
- drawdown before target
- time-to-peak reaction
- decay profile

## Calibration Outputs

Calibration should produce versioned parameter sets:

- event-type base confidence adjustments
- source credibility adjustments
- freshness half-life updates
- impact multipliers by relationship type
- persistence priors by event subtype
- duplicate/update weighting rules
- minimum confidence thresholds by strategy role
- veto/confirmation thresholds

These outputs should be stored separately from raw events and should have:

- calibration version
- training data date range
- sample size
- excluded symbols/sources
- validation period
- generated timestamp

## Avoiding Leakage

Calibration must avoid using information that was unavailable at event time.

Rules:

- use event timestamp as the anchor
- only include source facts available at that timestamp
- distinguish original article from material updates
- evaluate each signal snapshot separately
- do not let final cluster state leak into earlier snapshot evaluation
- separate training and validation periods

## Suggested Architecture

```text
Persisted event/signal snapshots
-> market data join
-> outcome window builder
-> calibration dataset
-> calibration analysis
-> versioned calibration parameters
-> deterministic pipeline config updates
```

The first implementation can be offline and file-based. It does not need to run inside the live ingestion process.

## Event Timing

Calibration should distinguish the factual event timestamp from the first practical trading anchor.

Stored/derived timestamps should include:

- `event_effective_at`: when the event factually relates to
- `first_publication_at`: when the market could first learn it
- `market_anchor_at`: the first usable tradable timestamp for outcome measurement

Initial session handling:

| Situation | Anchor |
| --- | --- |
| Regular-session news | event timestamp, or first cached bar at/after event |
| Pre-market news | same-day regular open unless pre-market bars are explicitly supplied |
| After-hours news | first cached after-hours bar if supplied, otherwise next regular open |
| Weekend or holiday | next regular open |
| Late SEC filing | filing acceptance time remains factual; next tradable timestamp is the market anchor |

Missing intraday data should not be fabricated. The fallback order is:

```text
1m bars
-> 5m bars
-> 1h bars
-> daily bars
-> outcome unavailable
```

Outcomes calculated from fallback data must mark the result as partial.

## Minimum v0.4 Acceptance Criteria

- Build a calibration dataset from persisted event/signal snapshots.
- Join outcomes for at least one liquid US share and related ETF.
- Calculate returns over fixed forward windows.
- Report event-type and source-type outcome summaries.
- Generate a versioned calibration report.
- Do not modify live scoring automatically.

Implemented first slice:

- favourites universe config in `config/favourites.yaml`
- calibration report endpoint at `GET /calibration/report`
- report scaffolding with fixed outcome windows
- EODHD market-data config and gitignored local token support
- structured `market_bars` cache
- market-data retention layers
- event timing anchor helper
- no automatic live-score mutation

## Later Extensions

- per-symbol and per-sector calibration
- source-specific priors
- event-subtype half-life estimation
- regime-aware calibration
- volatility and liquidity filters
- walk-forward validation
- optional ML model trained from deterministic labels
