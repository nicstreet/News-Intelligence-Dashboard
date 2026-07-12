from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime
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


class StorageLayerSummaryService:
    def __init__(
        self,
        config: NewsIntelligenceConfig,
        repositories: RepositoryBundle,
    ) -> None:
        self._config = config
        self._repositories = repositories

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
            "generated_at": now_utc().isoformat(),
            "database_path": str(self._repositories.db_path),
            "database_file_bytes": self._file_size(self._repositories.db_path),
            "total_current_bytes": sum(int(layer["current_bytes"]) for layer in layers),
            "total_projected_bytes": sum(int(layer["projected_bytes"]) for layer in layers),
            "layers": layers,
        }

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
