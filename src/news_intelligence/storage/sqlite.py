from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel


def _utc_iso() -> str:
    return datetime.now(UTC).isoformat()


class JsonRecordRepository:
    def __init__(self, db_path: Path, table_name: str) -> None:
        self.db_path = db_path
        self.table_name = table_name
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialise()

    def save(self, record_id: str, payload: BaseModel | dict[str, Any]) -> None:
        payload_json = self._payload_json(payload)
        timestamp = _utc_iso()
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                f"""
                INSERT INTO {self.table_name} (id, payload_json, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (record_id, payload_json, timestamp, timestamp),
            )

    def delete(self, record_id: str) -> int:
        with sqlite3.connect(self.db_path) as connection:
            cursor = connection.execute(
                f"DELETE FROM {self.table_name} WHERE id = ?",
                (record_id,),
            )
            return cursor.rowcount

    def delete_where(self, predicate: Callable[[dict[str, Any]], bool]) -> int:
        deleted = 0
        with sqlite3.connect(self.db_path) as connection:
            rows = connection.execute(f"SELECT id, payload_json FROM {self.table_name}").fetchall()
        for record_id, payload_json in rows:
            payload = json.loads(str(payload_json))
            if isinstance(record_id, str) and isinstance(payload, dict) and predicate(payload):
                deleted += self.delete(record_id)
        return deleted

    def get(self, record_id: str) -> dict[str, Any] | None:
        with sqlite3.connect(self.db_path) as connection:
            row = connection.execute(
                f"SELECT payload_json FROM {self.table_name} WHERE id = ?",
                (record_id,),
            ).fetchone()
        if row is None:
            return None
        payload = json.loads(str(row[0]))
        return payload if isinstance(payload, dict) else None

    def list_recent(self, limit: int = 50) -> list[dict[str, Any]]:
        with sqlite3.connect(self.db_path) as connection:
            rows = connection.execute(
                f"SELECT payload_json FROM {self.table_name} ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        records: list[dict[str, Any]] = []
        for row in rows:
            payload = json.loads(str(row[0]))
            if isinstance(payload, dict):
                records.append(payload)
        return records

    def list_all(self) -> list[dict[str, Any]]:
        with sqlite3.connect(self.db_path) as connection:
            rows = connection.execute(f"SELECT payload_json FROM {self.table_name}").fetchall()
        records: list[dict[str, Any]] = []
        for row in rows:
            payload = json.loads(str(row[0]))
            if isinstance(payload, dict):
                records.append(payload)
        return records

    def get_by_symbol(self, symbol: str, limit: int = 20) -> list[dict[str, Any]]:
        wanted = symbol.upper()
        matches: list[dict[str, Any]] = []
        for payload in self.list_recent(500):
            instrument = payload.get("instrument", {})
            if isinstance(instrument, dict) and str(instrument.get("symbol", "")).upper() == wanted:
                matches.append(payload)
            if len(matches) >= limit:
                break
        return matches

    def _initialise(self) -> None:
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self.table_name} (
                    id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def _payload_json(self, payload: BaseModel | dict[str, Any]) -> str:
        if isinstance(payload, BaseModel):
            return payload.model_dump_json()
        return json.dumps(payload, sort_keys=True, default=str)


class RepositoryBundle:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.raw_news = JsonRecordRepository(db_path, "raw_news")
        self.normalised_news = JsonRecordRepository(db_path, "normalised_news")
        self.events = JsonRecordRepository(db_path, "events")
        self.clusters = JsonRecordRepository(db_path, "event_clusters")
        self.impacts = JsonRecordRepository(db_path, "instrument_impacts")
        self.signals = JsonRecordRepository(db_path, "signal_snapshots")
        self.source_filings = JsonRecordRepository(db_path, "source_filings")
        self.source_status = JsonRecordRepository(db_path, "source_status")
        self.automation_runs = JsonRecordRepository(db_path, "automation_runs")

    def delete_test_run(self, test_run_id: str) -> dict[str, int]:
        return {
            name: repository.delete_where(
                lambda payload: payload.get("test_run_id") == test_run_id
            )
            for name, repository in self._repositories().items()
        }

    def delete_development_data(self) -> dict[str, int]:
        return {
            name: repository.delete_where(self._is_development_or_test_record)
            for name, repository in self._repositories().items()
        }

    def _repositories(self) -> dict[str, JsonRecordRepository]:
        return {
            "raw_news": self.raw_news,
            "normalised_news": self.normalised_news,
            "events": self.events,
            "event_clusters": self.clusters,
            "instrument_impacts": self.impacts,
            "signal_snapshots": self.signals,
            "source_filings": self.source_filings,
            "source_status": self.source_status,
            "automation_runs": self.automation_runs,
        }

    def _is_development_or_test_record(self, payload: dict[str, Any]) -> bool:
        environment = payload.get("record_environment")
        if environment == "production":
            return False
        return environment in {"development", "test", None}
