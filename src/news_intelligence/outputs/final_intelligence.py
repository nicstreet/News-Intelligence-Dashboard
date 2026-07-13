from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from news_intelligence.calibration.outcomes import JoinedOutcomeAnalysisService
from news_intelligence.config import NewsIntelligenceConfig
from news_intelligence.storage import RepositoryBundle
from news_intelligence.universe import FavouritesUniverseService
from news_intelligence.utils import now_utc, stable_hash


class FinalIntelligenceOutputService:
    """Creates the compact user-facing output records and writes delta JSON."""

    def __init__(
        self,
        config: NewsIntelligenceConfig,
        repositories: RepositoryBundle,
    ) -> None:
        self._config = config
        self._repositories = repositories

    def records(self, *, limit: int = 500) -> list[dict[str, Any]]:
        outcomes = JoinedOutcomeAnalysisService(
            self._repositories,
            FavouritesUniverseService(self._config),
        ).outcomes(limit=limit)
        events_by_id = {
            str(event.get("event_id", "")): event
            for event in self._repositories.events.list_recent(limit)
        }
        signals_by_id = {
            str(signal.get("signal_id", "")): signal
            for signal in self._repositories.signals.list_recent(limit)
        }
        records: list[dict[str, Any]] = []
        for outcome in outcomes.get("rows", []):
            if not isinstance(outcome, dict):
                continue
            event = events_by_id.get(str(outcome.get("event_id", "")), {})
            signal = signals_by_id.get(str(outcome.get("signal_id", "")), {})
            records.append(
                self._record_from_joined_row(
                    outcome=outcome,
                    event=event,
                    signal=signal,
                )
            )
        records.sort(key=lambda record: str(record.get("event_time", "")), reverse=True)
        return records

    def list_output(self, *, limit: int = 500) -> dict[str, Any]:
        records = self.records(limit=limit)
        stored = {
            str(payload.get("record_id")): payload
            for payload in self._repositories.final_outputs.list_recent(limit)
        }
        decorated: list[dict[str, Any]] = []
        for record in records:
            status = stored.get(str(record["record_id"]), {})
            decorated.append(
                {
                    **record,
                    "export_status": {
                        "exported": bool(status.get("exported")),
                        "exported_at": status.get("exported_at"),
                        "path": status.get("path"),
                        "content_hash": status.get("content_hash"),
                    },
                }
            )
        return {
            "schema_version": "1.0.0",
            "generated_at": now_utc().isoformat(),
            "record_count": len(decorated),
            "records": decorated,
        }

    def export_delta(
        self,
        *,
        limit: int = 500,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        output_dir = self._output_dir()
        output_dir.mkdir(parents=True, exist_ok=True)
        started_at = now_utc()
        records = self.records(limit=limit)
        exported: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        run_identifier = run_id or stable_hash(started_at.isoformat(), prefix="run_", length=12)
        for record in records:
            content_hash = self._content_hash(record)
            previous = self._repositories.final_outputs.get(str(record["record_id"]))
            if previous and previous.get("content_hash") == content_hash:
                skipped.append({"record_id": record["record_id"], "reason": "unchanged"})
                continue
            filename = self._filename(record, content_hash)
            final_path = self._atomic_write(output_dir / filename, record)
            exported_record = {
                **record,
                "content_hash": content_hash,
                "path": str(final_path),
                "exported": True,
                "exported_at": now_utc().isoformat(),
            }
            self._repositories.final_outputs.save(str(record["record_id"]), exported_record)
            exported.append(
                {
                    "record_id": record["record_id"],
                    "path": str(final_path),
                    "content_hash": content_hash,
                }
            )
        manifest = {
            "schema_version": "1.0.0",
            "producer": "asterius_news_intelligence",
            "run_id": run_identifier,
            "started_at": started_at.isoformat(),
            "completed_at": now_utc().isoformat(),
            "records_considered": len(records),
            "records_exported": len(exported),
            "records_skipped": len(skipped),
            "files": exported,
            "skipped": skipped,
        }
        manifest_path = self._atomic_write(
            output_dir / f"{run_identifier}_manifest.json",
            manifest,
        )
        return {**manifest, "manifest_path": str(manifest_path)}

    def _record_from_joined_row(
        self,
        *,
        outcome: dict[str, Any],
        event: dict[str, Any],
        signal: dict[str, Any],
    ) -> dict[str, Any]:
        signal_metrics = signal.get("signal", {}) if isinstance(signal.get("signal"), dict) else {}
        decision = signal.get("decision", {}) if isinstance(signal.get("decision"), dict) else {}
        source = event.get("source", {}) if isinstance(event.get("source"), dict) else {}
        record_id = stable_hash(
            outcome.get("signal_id"),
            outcome.get("event_id"),
            outcome.get("symbol"),
            prefix="intel_",
            length=16,
        )
        return {
            "schema_version": "1.0.0",
            "record_id": record_id,
            "event_id": outcome.get("event_id"),
            "signal_id": outcome.get("signal_id"),
            "cluster_id": outcome.get("cluster_id"),
            "event_time": outcome.get("event_time"),
            "headline": outcome.get("headline"),
            "event_type": outcome.get("event_type"),
            "event_subtype": outcome.get("event_subtype"),
            "event_status": outcome.get("event_status"),
            "scope": event.get("event_scope"),
            "instrument": {
                "symbol": outcome.get("symbol"),
                "exchange": outcome.get("exchange"),
                "benchmark_symbol": outcome.get("benchmark_symbol"),
            },
            "signal": {
                "direction": signal_metrics.get("direction") or outcome.get("direction"),
                "signal_score": signal_metrics.get("signal_score") or outcome.get("signal_score"),
                "confidence": signal_metrics.get("confidence") or outcome.get("confidence"),
                "quality": signal_metrics.get("quality") or outcome.get("quality"),
                "freshness": signal_metrics.get("freshness"),
                "strength": signal_metrics.get("strength"),
                "can_trigger_trade": decision.get("can_trigger_trade"),
                "can_confirm_trade": decision.get("can_confirm_trade"),
                "can_veto_trade": decision.get("can_veto_trade"),
            },
            "market_reaction": {
                "market_anchor_at": outcome.get("market_anchor_at"),
                "market_session": outcome.get("market_session"),
                "price_at_event": outcome.get("price_at_event"),
                "returns": outcome.get("returns", {}),
                "benchmark_returns": outcome.get("benchmark_returns", {}),
                "abnormal_returns": outcome.get("abnormal_returns", {}),
                "maximum_favourable_excursion_5d": outcome.get(
                    "maximum_favourable_excursion_5d"
                ),
                "maximum_adverse_excursion_5d": outcome.get("maximum_adverse_excursion_5d"),
                "outcome_status": outcome.get("outcome_status"),
            },
            "source": {
                "source_name": source.get("source_name"),
                "source_type": source.get("source_type"),
                "source_url": source.get("source_url"),
                "source_credibility": source.get("source_credibility"),
            },
            "audit": {
                "calibration_profile": outcome.get("calibration_profile"),
                "confounder_grade": outcome.get("confounder_grade"),
                "bars_available": outcome.get("bars_available"),
                "notes": outcome.get("notes", []),
                "record_environment": signal.get("record_environment"),
                "test_run_id": signal.get("test_run_id"),
            },
        }

    def _content_hash(self, payload: dict[str, Any]) -> str:
        clean = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return stable_hash(clean, prefix="sha256_", length=24)

    def _filename(self, record: dict[str, Any], content_hash: str) -> str:
        symbol = str(record.get("instrument", {}).get("symbol", "UNKNOWN")).replace(".", "_")
        event_time = str(record.get("event_time", "")).replace(":", "").replace("-", "")
        safe_time = event_time.replace("+", "Z").replace(".", "")[:24] or "unknown_time"
        return f"{safe_time}_{symbol}_{record['record_id']}_{content_hash[-8:]}.json"

    def _atomic_write(self, path: Path, payload: dict[str, Any]) -> Path:
        tmp_path = path.with_suffix(f"{path.suffix}.tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, default=str)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        tmp_path.replace(path)
        return path

    def _output_dir(self) -> Path:
        configured = Path(str(self._config.file_drop.get("output_dir", "file_drop/outbox")))
        if configured.is_absolute():
            return configured
        return self._config.root / configured
