from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Iterator, Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from news_intelligence.config import NewsIntelligenceConfig
from news_intelligence.storage import JsonRecordRepository, RepositoryBundle
from news_intelligence.utils import now_utc, to_utc

TIMESTAMP_KEYS = {
    "published_at",
    "first_seen_at",
    "processed_at",
    "event_effective_at",
    "generated_at",
    "expires_at",
    "expiry_time",
    "filing_time",
    "ingested_at",
    "created_at",
    "updated_at",
    "first_publication_at",
    "latest_article_at",
    "latest_material_update_at",
}

SYMBOL_KEYS = {
    "known_ticker",
    "symbol",
    "ticker",
    "primary_symbol",
}

SYMBOL_LIST_KEYS = {
    "tickers",
    "detected_symbols",
    "entity_symbols",
    "affected_instruments",
}

REPOSITORY_LAYER_KEYS = {
    "raw_news",
    "normalised_news",
    "events",
    "event_clusters",
    "instrument_impacts",
    "signal_snapshots",
    "source_filings",
}

RETENTION_TIMESTAMP_PRIORITY = (
    "generated_at",
    "processed_at",
    "published_at",
    "first_seen_at",
    "ingested_at",
    "filing_time",
    "expires_at",
    "expiry_time",
    "updated_at",
    "created_at",
    "latest_article_at",
)

FILE_DROP_DIRECTORIES = ("output_dir", "archive_dir", "error_dir")


class StorageLayerSummaryService:
    def __init__(
        self,
        config: NewsIntelligenceConfig,
        repositories: RepositoryBundle,
        clock: Callable[[], datetime] = now_utc,
    ) -> None:
        self._config = config
        self._repositories = repositories
        self._clock = clock

    def summary(self) -> dict[str, Any]:
        layers = [
            self._repository_layer("raw_news", self._repositories.raw_news),
            self._repository_layer("normalised_news", self._repositories.normalised_news),
            self._repository_layer("events", self._repositories.events),
            self._repository_layer("event_clusters", self._repositories.clusters),
            self._repository_layer("instrument_impacts", self._repositories.impacts),
            self._repository_layer("signal_snapshots", self._repositories.signals),
            self._repository_layer("source_filings", self._repositories.source_filings),
            self._file_drop_layer(),
            self._empty_layer("calibration"),
        ]
        return {
            "schema_version": "1.0.0",
            "retention_version": str(self._config.retention.get("version", "retention-unknown")),
            "generated_at": self._clock().isoformat(),
            "database_path": str(self._repositories.db_path),
            "database_file_bytes": self._file_size(self._repositories.db_path),
            "total_current_bytes": sum(int(layer["current_bytes"]) for layer in layers),
            "total_projected_bytes": sum(int(layer["projected_bytes"]) for layer in layers),
            "layers": layers,
        }

    def retention_plan(
        self,
        retention_days: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._retention_plan(retention_days, apply_changes=False)

    def apply_retention(
        self,
        retention_days: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._retention_plan(retention_days, apply_changes=True)

    def _repository_layer(
        self,
        layer_key: str,
        repository: JsonRecordRepository,
    ) -> dict[str, Any]:
        current_bytes = 0
        record_count = 0
        timestamps: list[datetime] = []
        tickers: set[str] = set()

        for payload_json in self._repository_payload_json(repository):
            current_bytes += len(payload_json.encode("utf-8"))
            record_count += 1
            try:
                payload = json.loads(payload_json)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            timestamps.extend(self._timestamps_from_payload(payload))
            tickers.update(self._symbols_from_payload(payload))

        return self._complete_layer(
            layer_key=layer_key,
            current_bytes=current_bytes,
            record_count=record_count,
            timestamps=timestamps,
            ticker_count=len(tickers),
        )

    def _file_drop_layer(self) -> dict[str, Any]:
        current_bytes = 0
        record_count = 0
        timestamps: list[datetime] = []
        tickers: set[str] = set()
        directories = [
            self._file_drop_path("output_dir"),
            self._file_drop_path("archive_dir"),
            self._file_drop_path("error_dir"),
        ]

        for directory in directories:
            if not directory.exists():
                continue
            for path in directory.rglob("*.json"):
                if not path.is_file():
                    continue
                stat = path.stat()
                current_bytes += stat.st_size
                record_count += 1
                timestamps.append(datetime.fromtimestamp(stat.st_mtime, tz=UTC))
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if isinstance(payload, dict):
                    timestamps.extend(self._timestamps_from_payload(payload))
                    tickers.update(self._symbols_from_payload(payload))

        layer = self._complete_layer(
            layer_key="file_drop",
            current_bytes=current_bytes,
            record_count=record_count,
            timestamps=timestamps,
            ticker_count=len(tickers),
        )
        layer["directories"] = [str(directory) for directory in directories]
        return layer

    def _empty_layer(self, layer_key: str) -> dict[str, Any]:
        return self._complete_layer(
            layer_key=layer_key,
            current_bytes=0,
            record_count=0,
            timestamps=[],
            ticker_count=0,
        )

    def _complete_layer(
        self,
        *,
        layer_key: str,
        current_bytes: int,
        record_count: int,
        timestamps: list[datetime],
        ticker_count: int,
    ) -> dict[str, Any]:
        settings = self._layer_settings(layer_key)
        retention_days = settings.get("retention_days")
        days_worth = self._days_worth(timestamps)
        estimated_bytes_per_day = (
            current_bytes / max(days_worth, 1.0) if record_count > 0 else 0.0
        )
        adjustable = bool(settings.get("adjustable", False))
        projected_bytes = current_bytes
        if adjustable and isinstance(retention_days, int) and retention_days > 0:
            projected_bytes = round(estimated_bytes_per_day * retention_days)

        return {
            "layer_key": layer_key,
            "layer_name": str(settings.get("label", layer_key.replace("_", " ").title())),
            "description": str(settings.get("description", "")),
            "current_bytes": current_bytes,
            "current_mb": round(current_bytes / 1_048_576, 4),
            "record_count": record_count,
            "days_worth": days_worth,
            "ticker_count": ticker_count,
            "retention_days": retention_days if isinstance(retention_days, int) else None,
            "adjustable": adjustable,
            "estimated_bytes_per_day": round(estimated_bytes_per_day, 2),
            "projected_bytes": projected_bytes,
            "projected_mb": round(projected_bytes / 1_048_576, 4),
        }

    def _repository_payload_json(
        self,
        repository: JsonRecordRepository,
    ) -> Iterator[str]:
        with sqlite3.connect(repository.db_path) as connection:
            cursor = connection.execute(f"SELECT payload_json FROM {repository.table_name}")
            while True:
                rows = cursor.fetchmany(500)
                if not rows:
                    break
                for row in rows:
                    yield str(row[0])

    def _retention_plan(
        self,
        retention_days: Mapping[str, Any] | None,
        *,
        apply_changes: bool,
    ) -> dict[str, Any]:
        overrides = self._normalise_retention_overrides(retention_days)
        layers = [
            self._repository_retention_plan(
                "raw_news",
                self._repositories.raw_news,
                overrides,
                apply_changes=apply_changes,
            ),
            self._repository_retention_plan(
                "normalised_news",
                self._repositories.normalised_news,
                overrides,
                apply_changes=apply_changes,
            ),
            self._retention_not_adjustable("events"),
            self._retention_not_adjustable("event_clusters"),
            self._repository_retention_plan(
                "instrument_impacts",
                self._repositories.impacts,
                overrides,
                apply_changes=apply_changes,
            ),
            self._repository_retention_plan(
                "signal_snapshots",
                self._repositories.signals,
                overrides,
                apply_changes=apply_changes,
            ),
            self._retention_not_adjustable("source_filings"),
            self._file_drop_retention_plan(overrides, apply_changes=apply_changes),
            self._retention_not_adjustable("calibration"),
        ]
        return {
            "schema_version": "1.0.0",
            "retention_version": str(self._config.retention.get("version", "retention-unknown")),
            "mode": "applied" if apply_changes else "dry_run",
            "generated_at": self._clock().isoformat(),
            "safety": (
                "Only development/test/unlabelled records are eligible; "
                "production-labelled records are retained."
            ),
            "total_candidate_records": sum(int(layer["candidate_records"]) for layer in layers),
            "total_candidate_bytes": sum(int(layer["candidate_bytes"]) for layer in layers),
            "total_deleted_records": sum(int(layer["deleted_records"]) for layer in layers),
            "total_deleted_bytes": sum(int(layer["deleted_bytes"]) for layer in layers),
            "layers": layers,
        }

    def _repository_retention_plan(
        self,
        layer_key: str,
        repository: JsonRecordRepository,
        overrides: Mapping[str, int],
        *,
        apply_changes: bool,
    ) -> dict[str, Any]:
        retention_days = self._effective_retention_days(layer_key, overrides)
        if retention_days is None:
            return self._retention_not_adjustable(layer_key)

        cutoff = self._clock() - timedelta(days=retention_days)
        candidate_ids: list[str] = []
        candidate_bytes = 0
        skipped_production = 0
        skipped_missing_timestamp = 0

        for record_id, payload_json in self._repository_rows(repository):
            try:
                payload = json.loads(payload_json)
            except json.JSONDecodeError:
                skipped_missing_timestamp += 1
                continue
            if not isinstance(payload, dict):
                skipped_missing_timestamp += 1
                continue
            if self._is_production_record(payload):
                skipped_production += 1
                continue
            timestamp = self._retention_timestamp(payload)
            if timestamp is None:
                skipped_missing_timestamp += 1
                continue
            if timestamp < cutoff:
                candidate_ids.append(record_id)
                candidate_bytes += len(payload_json.encode("utf-8"))

        deleted_records = 0
        if apply_changes:
            deleted_records = self._delete_repository_records(repository, candidate_ids)

        return self._retention_layer_payload(
            layer_key=layer_key,
            retention_days=retention_days,
            cutoff=cutoff,
            candidate_records=len(candidate_ids),
            candidate_bytes=candidate_bytes,
            deleted_records=deleted_records,
            deleted_bytes=candidate_bytes if apply_changes else 0,
            skipped_production_records=skipped_production,
            skipped_missing_timestamp_records=skipped_missing_timestamp,
        )

    def _file_drop_retention_plan(
        self,
        overrides: Mapping[str, int],
        *,
        apply_changes: bool,
    ) -> dict[str, Any]:
        retention_days = self._effective_retention_days("file_drop", overrides)
        if retention_days is None:
            return self._retention_not_adjustable("file_drop")

        cutoff = self._clock() - timedelta(days=retention_days)
        candidate_paths: list[Path] = []
        candidate_bytes = 0
        skipped_production = 0
        skipped_missing_timestamp = 0
        directories = [self._file_drop_path(key) for key in FILE_DROP_DIRECTORIES]

        for directory in directories:
            if not directory.exists():
                continue
            root = directory.resolve()
            for path in directory.rglob("*.json"):
                if not path.is_file():
                    continue
                resolved = path.resolve()
                if not resolved.is_relative_to(root):
                    continue
                payload = self._json_file_payload(path)
                if payload is not None and self._is_production_record(payload):
                    skipped_production += 1
                    continue
                timestamp = (
                    self._retention_timestamp(payload)
                    if payload is not None
                    else datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
                )
                if timestamp is None:
                    skipped_missing_timestamp += 1
                    continue
                if timestamp < cutoff:
                    candidate_paths.append(path)
                    candidate_bytes += self._file_size(path)

        deleted_records = 0
        if apply_changes:
            deleted_records = self._delete_files(candidate_paths)

        layer = self._retention_layer_payload(
            layer_key="file_drop",
            retention_days=retention_days,
            cutoff=cutoff,
            candidate_records=len(candidate_paths),
            candidate_bytes=candidate_bytes,
            deleted_records=deleted_records,
            deleted_bytes=candidate_bytes if apply_changes else 0,
            skipped_production_records=skipped_production,
            skipped_missing_timestamp_records=skipped_missing_timestamp,
        )
        layer["directories"] = [str(directory) for directory in directories]
        return layer

    def _retention_not_adjustable(self, layer_key: str) -> dict[str, Any]:
        return self._retention_layer_payload(
            layer_key=layer_key,
            retention_days=None,
            cutoff=None,
            candidate_records=0,
            candidate_bytes=0,
            deleted_records=0,
            deleted_bytes=0,
            skipped_production_records=0,
            skipped_missing_timestamp_records=0,
        )

    def _retention_layer_payload(
        self,
        *,
        layer_key: str,
        retention_days: int | None,
        cutoff: datetime | None,
        candidate_records: int,
        candidate_bytes: int,
        deleted_records: int,
        deleted_bytes: int,
        skipped_production_records: int,
        skipped_missing_timestamp_records: int,
    ) -> dict[str, Any]:
        settings = self._layer_settings(layer_key)
        return {
            "layer_key": layer_key,
            "layer_name": str(settings.get("label", layer_key.replace("_", " ").title())),
            "adjustable": bool(settings.get("adjustable", False)),
            "retention_days": retention_days,
            "cutoff_at": cutoff.isoformat() if cutoff is not None else None,
            "candidate_records": candidate_records,
            "candidate_bytes": candidate_bytes,
            "deleted_records": deleted_records,
            "deleted_bytes": deleted_bytes,
            "skipped_production_records": skipped_production_records,
            "skipped_missing_timestamp_records": skipped_missing_timestamp_records,
        }

    def _repository_rows(
        self,
        repository: JsonRecordRepository,
    ) -> Iterator[tuple[str, str]]:
        with sqlite3.connect(repository.db_path) as connection:
            cursor = connection.execute(f"SELECT id, payload_json FROM {repository.table_name}")
            while True:
                rows = cursor.fetchmany(500)
                if not rows:
                    break
                for record_id, payload_json in rows:
                    yield str(record_id), str(payload_json)

    def _delete_repository_records(
        self,
        repository: JsonRecordRepository,
        record_ids: list[str],
    ) -> int:
        if not record_ids:
            return 0
        deleted = 0
        with sqlite3.connect(repository.db_path) as connection:
            for record_id in record_ids:
                cursor = connection.execute(
                    f"DELETE FROM {repository.table_name} WHERE id = ?",
                    (record_id,),
                )
                deleted += cursor.rowcount
        return deleted

    def _delete_files(self, paths: list[Path]) -> int:
        deleted = 0
        for path in paths:
            try:
                path.unlink()
            except FileNotFoundError:
                continue
            except OSError:
                continue
            deleted += 1
        return deleted

    def _normalise_retention_overrides(
        self,
        retention_days: Mapping[str, Any] | None,
    ) -> dict[str, int]:
        if retention_days is None:
            return {}
        overrides: dict[str, int] = {}
        for layer_key, value in retention_days.items():
            if layer_key not in {*REPOSITORY_LAYER_KEYS, "file_drop", "calibration"}:
                continue
            try:
                days = int(value)
            except (TypeError, ValueError):
                continue
            if days >= 1:
                overrides[str(layer_key)] = days
        return overrides

    def _effective_retention_days(
        self,
        layer_key: str,
        overrides: Mapping[str, int],
    ) -> int | None:
        settings = self._layer_settings(layer_key)
        if not bool(settings.get("adjustable", False)):
            return None
        configured = overrides.get(layer_key, settings.get("retention_days"))
        if not isinstance(configured, int) or configured <= 0:
            return None
        return configured

    def _is_production_record(self, payload: dict[str, Any]) -> bool:
        return self._record_environment(payload) == "production"

    def _record_environment(self, payload: dict[str, Any]) -> str | None:
        for candidate in (
            payload,
            payload.get("audit"),
            payload.get("signal"),
            payload.get("event"),
        ):
            if not isinstance(candidate, dict):
                continue
            environment = candidate.get("record_environment")
            if isinstance(environment, str) and environment:
                return environment
        return None

    def _retention_timestamp(self, payload: dict[str, Any] | None) -> datetime | None:
        if payload is None:
            return None
        for key in RETENTION_TIMESTAMP_PRIORITY:
            timestamp = self._parse_datetime(payload.get(key))
            if timestamp is not None:
                return timestamp

        nested = payload.get("timestamps")
        if isinstance(nested, dict):
            for key in RETENTION_TIMESTAMP_PRIORITY:
                timestamp = self._parse_datetime(nested.get(key))
                if timestamp is not None:
                    return timestamp

        audit = payload.get("audit")
        if isinstance(audit, dict):
            for key in RETENTION_TIMESTAMP_PRIORITY:
                timestamp = self._parse_datetime(audit.get(key))
                if timestamp is not None:
                    return timestamp
        return None

    def _json_file_payload(self, path: Path) -> dict[str, Any] | None:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def _timestamps_from_payload(self, payload: dict[str, Any]) -> list[datetime]:
        timestamps: list[datetime] = []
        for key in TIMESTAMP_KEYS:
            timestamp = self._parse_datetime(payload.get(key))
            if timestamp is not None:
                timestamps.append(timestamp)

        nested = payload.get("timestamps")
        if isinstance(nested, dict):
            for key in TIMESTAMP_KEYS:
                timestamp = self._parse_datetime(nested.get(key))
                if timestamp is not None:
                    timestamps.append(timestamp)

        audit = payload.get("audit")
        if isinstance(audit, dict):
            for key in TIMESTAMP_KEYS:
                timestamp = self._parse_datetime(audit.get(key))
                if timestamp is not None:
                    timestamps.append(timestamp)
        return timestamps

    def _symbols_from_payload(self, payload: dict[str, Any]) -> set[str]:
        symbols: set[str] = set()
        for key in SYMBOL_KEYS:
            self._add_symbol(symbols, payload.get(key))
        for key in SYMBOL_LIST_KEYS:
            self._add_symbols(symbols, payload.get(key))

        instrument = payload.get("instrument")
        if isinstance(instrument, dict):
            self._add_symbol(symbols, instrument.get("symbol"))

        signal = payload.get("signal")
        if isinstance(signal, dict):
            nested_instrument = signal.get("instrument")
            if isinstance(nested_instrument, dict):
                self._add_symbol(symbols, nested_instrument.get("symbol"))

        entities = payload.get("entities")
        if isinstance(entities, list):
            for entity in entities:
                if isinstance(entity, dict):
                    self._add_symbol(symbols, entity.get("symbol"))

        impacts = payload.get("impacts")
        if isinstance(impacts, list):
            for impact in impacts:
                if isinstance(impact, dict):
                    self._add_symbol(symbols, impact.get("symbol"))
        return symbols

    def _add_symbols(self, symbols: set[str], value: object) -> None:
        if isinstance(value, list):
            for item in value:
                self._add_symbol(symbols, item)
        elif isinstance(value, dict):
            for item in value.values():
                self._add_symbol(symbols, item)

    def _add_symbol(self, symbols: set[str], value: object) -> None:
        if not isinstance(value, str):
            return
        symbol = value.strip().upper()
        if not symbol or symbol in {"N/A", "NONE", "NULL"}:
            return
        symbols.add(symbol)

    def _days_worth(self, timestamps: list[datetime]) -> int:
        if not timestamps:
            return 0
        start = min(timestamps)
        end = max(timestamps)
        return max(1, (end.date() - start.date()).days + 1)

    def _parse_datetime(self, value: object) -> datetime | None:
        if isinstance(value, datetime):
            return to_utc(value)
        if not isinstance(value, str) or not value.strip():
            return None
        candidate = value.strip()
        if candidate.endswith("Z"):
            candidate = f"{candidate[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            return None
        return to_utc(parsed)

    def _layer_settings(self, layer_key: str) -> dict[str, Any]:
        layers = self._config.retention.get("layers", {})
        if not isinstance(layers, dict):
            return {}
        settings = layers.get(layer_key, {})
        return settings if isinstance(settings, dict) else {}

    def _file_drop_path(self, key: str) -> Path:
        configured = Path(str(self._config.file_drop.get(key, f"file_drop/{key}")))
        if configured.is_absolute():
            return configured
        return self._config.root / configured

    def _file_size(self, path: Path) -> int:
        try:
            return path.stat().st_size
        except OSError:
            return 0
