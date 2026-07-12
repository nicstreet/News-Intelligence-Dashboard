from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from news_intelligence.config import NewsIntelligenceConfig
from news_intelligence.storage import RepositoryBundle
from news_intelligence.utils import now_utc


class FileDropExporter:
    def __init__(
        self,
        config: NewsIntelligenceConfig,
        repositories: RepositoryBundle,
    ) -> None:
        self._config = config
        self._repositories = repositories
        self._settings = config.file_drop

    def status(self) -> dict[str, Any]:
        output_dir = self._path("output_dir")
        return {
            "enabled": bool(self._settings.get("enabled", False)),
            "output_dir": str(output_dir),
            "archive_dir": str(self._path("archive_dir")),
            "error_dir": str(self._path("error_dir")),
            "schema_version": str(self._settings.get("schema_version", "1.0.0")),
            "output_dir_exists": output_dir.exists(),
        }

    def export_signal(self, signal_id: str) -> dict[str, Any]:
        signal = self._repositories.signals.get(signal_id)
        if signal is None:
            raise KeyError(signal_id)
        payload = self._payload(signal)
        output_dir = self._path("output_dir")
        output_dir.mkdir(parents=True, exist_ok=True)
        filename = self._filename(payload)
        tmp_path = output_dir / f"{filename}.tmp"
        final_path = output_dir / f"{filename}.json"
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, default=str)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        tmp_path.replace(final_path)
        return {"path": str(final_path), "payload": payload}

    def export_latest(self, *, limit: int = 20) -> list[dict[str, Any]]:
        exported: list[dict[str, Any]] = []
        for signal in self._repositories.signals.list_recent(limit):
            signal_id = str(signal.get("signal_id", ""))
            if signal_id:
                exported.append(self.export_signal(signal_id))
        return exported

    def _payload(self, signal: dict[str, Any]) -> dict[str, Any]:
        event = self._repositories.events.get(str(signal.get("event_id", ""))) or {}
        cluster = self._repositories.clusters.get(str(signal.get("cluster_id", ""))) or {}
        source = event.get("source", {}) if isinstance(event.get("source"), dict) else {}
        return {
            "schema_version": str(self._settings.get("schema_version", "1.0.0")),
            "producer": "asterius_news_intelligence",
            "generated_at": now_utc().isoformat(),
            "signal": signal,
            "event": event,
            "cluster": {
                "cluster_id": cluster.get("cluster_id"),
                "article_count": cluster.get("article_count"),
                "duplicate_count": cluster.get("duplicate_count"),
                "update_count": cluster.get("update_count"),
                "independent_source_count": cluster.get("independent_source_count"),
                "latest_article_at": cluster.get("latest_article_at"),
                "latest_material_update_at": cluster.get("latest_material_update_at"),
                "signal_snapshot_count": len(cluster.get("signal_snapshots", []))
                if isinstance(cluster.get("signal_snapshots"), list)
                else 0,
            },
            "source": source,
            "audit": {
                "record_environment": signal.get("record_environment"),
                "test_run_id": signal.get("test_run_id"),
                "event_id": signal.get("event_id"),
                "cluster_id": signal.get("cluster_id"),
                "signal_id": signal.get("signal_id"),
            },
        }

    def _filename(self, payload: dict[str, Any]) -> str:
        signal = payload.get("signal", {})
        instrument = signal.get("instrument", {}) if isinstance(signal, dict) else {}
        symbol = str(instrument.get("symbol", "UNKNOWN")).replace(".", "_")
        signal_id = str(signal.get("signal_id", "signal")) if isinstance(signal, dict) else "signal"
        generated_at = str(payload["generated_at"]).replace(":", "").replace("-", "")
        return f"{generated_at}_{symbol}_{signal_id}"

    def _path(self, key: str) -> Path:
        configured = Path(str(self._settings.get(key, f"file_drop/{key}")))
        if configured.is_absolute():
            return configured
        return self._config.root / configured
