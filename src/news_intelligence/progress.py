from __future__ import annotations

from datetime import UTC, datetime
from threading import RLock
from typing import Any


class RunProgressStore:
    def __init__(self) -> None:
        self._lock = RLock()
        self._runs: dict[str, dict[str, Any]] = {}
        self._latest_run_id: str | None = None

    def start(self, run_id: str, *, reason: str) -> dict[str, Any]:
        now = self._now()
        payload = {
            "run_id": run_id,
            "reason": reason,
            "status": "running",
            "phase": "starting",
            "message": "Starting run",
            "connector_name": None,
            "connector_index": 0,
            "connector_total": 0,
            "record_index": 0,
            "record_total": 0,
            "market_symbol": None,
            "market_symbol_index": 0,
            "market_symbol_total": 0,
            "fetched_count": 0,
            "ingested_count": 0,
            "skipped_count": 0,
            "exported_count": 0,
            "error_count": 0,
            "started_at": now,
            "updated_at": now,
            "completed_at": None,
        }
        with self._lock:
            self._runs[run_id] = payload
            self._latest_run_id = run_id
            return dict(payload)

    def update(self, run_id: str, **updates: Any) -> dict[str, Any]:
        with self._lock:
            payload = self._runs.get(run_id)
            if payload is None:
                now = self._now()
                payload = {
                    "run_id": run_id,
                    "reason": str(updates.get("reason", "unknown")),
                    "status": "running",
                    "phase": "starting",
                    "message": "Starting run",
                    "connector_name": None,
                    "connector_index": 0,
                    "connector_total": 0,
                    "record_index": 0,
                    "record_total": 0,
                    "market_symbol": None,
                    "market_symbol_index": 0,
                    "market_symbol_total": 0,
                    "fetched_count": 0,
                    "ingested_count": 0,
                    "skipped_count": 0,
                    "exported_count": 0,
                    "error_count": 0,
                    "started_at": now,
                    "updated_at": now,
                    "completed_at": None,
                }
                self._runs[run_id] = payload
                self._latest_run_id = run_id
            payload.update(updates)
            payload["updated_at"] = self._now()
            return dict(payload)

    def finish(
        self,
        run_id: str,
        *,
        status: str,
        message: str,
        **updates: Any,
    ) -> dict[str, Any]:
        now = self._now()
        return self.update(
            run_id,
            **updates,
            status=status,
            phase="complete" if status == "complete" else "error",
            message=message,
            completed_at=now,
        )

    def get(self, run_id: str | None = None) -> dict[str, Any] | None:
        with self._lock:
            selected = run_id or self._latest_run_id
            if selected is None:
                return None
            payload = self._runs.get(selected)
            return dict(payload) if payload is not None else None

    def _now(self) -> str:
        return datetime.now(UTC).isoformat()


progress_store = RunProgressStore()
