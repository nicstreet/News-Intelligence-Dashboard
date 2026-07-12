# File-Drop Integration Contract

The planned trading-app integration is a cleansed JSON file drop. Asterius News Intelligence will write signal files into a configured directory, and the trading application will ingest those files.

This keeps the news service independent from the trading app lifecycle and avoids coupling ingestion to dashboard state or internal SQLite tables.

## Integration Shape

```text
Asterius News Intelligence
-> validates and cleanses event/signal JSON
-> writes file atomically to output directory
-> trading app watches directory
-> trading app ingests and archives/acks file
```

The trading app remains responsible for:

- strategy rules
- indicator aggregation
- portfolio state
- order/risk controls
- broker connectivity
- duplicate handling on its own side

## Output Directory

Future config should include:

```yaml
file_drop:
  enabled: true
  output_dir: C:/path/to/news-signals/inbox
  archive_dir: C:/path/to/news-signals/archive
  error_dir: C:/path/to/news-signals/error
```

The writer should create files with a temporary extension first, then atomically rename after the full JSON payload is written.

Example:

```text
sig_abc123.tmp
sig_abc123.json
```

The trading app should only ingest `.json` files.

## File Naming

Suggested pattern:

```text
{generated_at_utc}_{symbol}_{signal_id}_{version}.json
```

Example:

```text
20260712T143012Z_AAPL_sig_7f3a2c_v2.json
```

Names should be stable, unique, and filesystem-safe.

## Payload Contract

The initial file-drop payload should be a cleansed subset of `NewsSignal` plus enough event/cluster context for the trading app to make a decision without querying this service.

Recommended top-level shape:

```json
{
  "schema_version": "1.0.0",
  "producer": "asterius_news_intelligence",
  "generated_at": "2026-07-12T14:30:12Z",
  "signal": {},
  "event": {},
  "cluster": {},
  "source": {},
  "audit": {}
}
```

## Recommended Fields

### Signal

- `signal_id`
- `version`
- `symbol`
- `direction`
- `directional_strength`
- `confidence`
- `quality`
- `freshness`
- `time_horizon`
- `expiry_time`
- `roles`
- `can_trigger_trade`
- `can_confirm_trade`
- `can_veto_trade`
- `requires_technical_confirmation`

### Event

- `event_id`
- `event_status`
- `event_type`
- `event_subtype`
- `headline`
- `summary`
- `published_at`
- `processed_at`
- `primary_symbol`
- `contradictions_detected`

### Cluster

- `cluster_id`
- `article_count`
- `duplicate_count`
- `update_count`
- `independent_source_count`
- `latest_article_at`
- `latest_material_update_at`
- `signal_snapshot_count`

### Source

- `source_name`
- `source_type`
- `source_url`
- `source_credibility`
- `source_record_id`
- `connector_type`

For SEC filings:

- `cik`
- `accession_number`
- `company`
- `form_type`
- `filing_time`
- `filing_sections`
- `filing_url`

### Audit

- `request_id`
- `record_environment`
- `test_run_id`
- `pipeline_version`
- `classifier_version`
- `entity_resolver_version`
- `clusterer_version`
- `scorer_version`

## Example

```json
{
  "schema_version": "1.0.0",
  "producer": "asterius_news_intelligence",
  "generated_at": "2026-07-12T14:30:12Z",
  "signal": {
    "signal_id": "sig_example",
    "version": 1,
    "symbol": "AAPL",
    "direction": "LONG",
    "directional_strength": 0.42,
    "confidence": 0.74,
    "quality": 0.88,
    "freshness": 0.97,
    "time_horizon": "INTRADAY",
    "expiry_time": "2026-07-12T22:30:12Z",
    "roles": ["RISK_OVERLAY"],
    "can_trigger_trade": false,
    "can_confirm_trade": false,
    "can_veto_trade": false,
    "requires_technical_confirmation": true
  },
  "event": {
    "event_id": "evt_example",
    "event_status": "confirmed",
    "event_type": "regulatory_legal",
    "event_subtype": "sec_8k_current_report",
    "headline": "APPLE INC files Form 8-K with SEC EDGAR",
    "summary": "SEC EDGAR Form 8-K current report filing.",
    "published_at": "2026-07-12T14:00:00Z",
    "processed_at": "2026-07-12T14:30:12Z",
    "primary_symbol": "AAPL",
    "contradictions_detected": false
  },
  "cluster": {
    "cluster_id": "cluster_example",
    "article_count": 1,
    "duplicate_count": 0,
    "update_count": 0,
    "independent_source_count": 1,
    "latest_article_at": "2026-07-12T14:00:00Z",
    "latest_material_update_at": "2026-07-12T14:00:00Z",
    "signal_snapshot_count": 1
  },
  "source": {
    "source_name": "SEC EDGAR",
    "source_type": "regulatory",
    "source_url": "https://www.sec.gov/Archives/...",
    "source_credibility": 0.96,
    "source_record_id": "sec_edgar:0000320193-26-000001",
    "connector_type": "sec_edgar",
    "cik": "0000320193",
    "accession_number": "0000320193-26-000001",
    "company": "APPLE INC",
    "form_type": "8-K",
    "filing_time": "2026-07-12T14:00:00Z",
    "filing_sections": ["8.01"],
    "filing_url": "https://www.sec.gov/Archives/..."
  },
  "audit": {
    "request_id": "req_example",
    "record_environment": "development",
    "test_run_id": null,
    "pipeline_version": "pipeline-1.0.0",
    "classifier_version": "rules-1.0.0",
    "entity_resolver_version": "resolver-1.0.0",
    "clusterer_version": "clusterer-1.0.0",
    "scorer_version": "freshness-unknown"
  }
}
```

## Atomic Write Rules

The writer should:

1. Build and validate JSON.
2. Write to a temp file in the same directory.
3. Flush and close the temp file.
4. Rename temp file to `.json`.
5. Never mutate a completed `.json` file.

The trading app should:

1. Watch for `.json` files only.
2. Open after file appears stable.
3. Validate schema version.
4. Deduplicate by `signal_id` and `version`.
5. Move processed files to archive or record ingestion state.

## Rebuild Note

The trading app ingestion model should be rebuilt after this contract is finalised. Until then, the news service should treat file-drop integration as a planned output adapter rather than a committed production interface.

