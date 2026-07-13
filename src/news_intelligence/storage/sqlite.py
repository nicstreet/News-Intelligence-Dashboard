from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from news_intelligence.models import MarketDataBar, MarketDataInterval


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


class MarketBarRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialise()

    def save_many(self, bars: list[MarketDataBar]) -> int:
        if not bars:
            return 0
        rows = [
            (
                bar.symbol.upper(),
                self._exchange_key(bar.exchange),
                bar.interval.value,
                bar.timestamp_utc.isoformat(),
                bar.open,
                bar.high,
                bar.low,
                bar.close,
                bar.adjusted_close,
                bar.volume,
                bar.source_name,
                bar.loaded_at.isoformat(),
                bar.record_environment.value,
            )
            for bar in bars
        ]
        with sqlite3.connect(self.db_path) as connection:
            connection.executemany(
                """
                INSERT INTO market_bars (
                    symbol,
                    exchange,
                    interval,
                    timestamp_utc,
                    open,
                    high,
                    low,
                    close,
                    adjusted_close,
                    volume,
                    source_name,
                    loaded_at,
                    record_environment
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, exchange, interval, timestamp_utc) DO UPDATE SET
                    open = excluded.open,
                    high = excluded.high,
                    low = excluded.low,
                    close = excluded.close,
                    adjusted_close = excluded.adjusted_close,
                    volume = excluded.volume,
                    source_name = excluded.source_name,
                    loaded_at = excluded.loaded_at,
                    record_environment = excluded.record_environment
                """,
                rows,
            )
        return len(rows)

    def list_range(
        self,
        *,
        symbol: str,
        interval: MarketDataInterval,
        start_at: datetime,
        end_at: datetime,
        exchange: str | None = None,
    ) -> list[MarketDataBar]:
        with sqlite3.connect(self.db_path) as connection:
            rows = connection.execute(
                """
                SELECT
                    symbol,
                    exchange,
                    interval,
                    timestamp_utc,
                    open,
                    high,
                    low,
                    close,
                    adjusted_close,
                    volume,
                    source_name,
                    loaded_at,
                    record_environment
                FROM market_bars
                WHERE symbol = ?
                  AND exchange = ?
                  AND interval = ?
                  AND timestamp_utc >= ?
                  AND timestamp_utc <= ?
                ORDER BY timestamp_utc ASC
                """,
                (
                    symbol.upper(),
                    self._exchange_key(exchange),
                    interval.value,
                    start_at.isoformat(),
                    end_at.isoformat(),
                ),
            ).fetchall()
        return [self._bar_from_row(row) for row in rows]

    def list_recent(self, limit: int = 50) -> list[dict[str, Any]]:
        with sqlite3.connect(self.db_path) as connection:
            rows = connection.execute(
                """
                SELECT
                    symbol,
                    exchange,
                    interval,
                    timestamp_utc,
                    open,
                    high,
                    low,
                    close,
                    adjusted_close,
                    volume,
                    source_name,
                    loaded_at,
                    record_environment
                FROM market_bars
                ORDER BY loaded_at DESC, timestamp_utc DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._bar_from_row(row).model_dump(mode="json") for row in rows]

    def coverage_summary(self) -> list[dict[str, Any]]:
        with sqlite3.connect(self.db_path) as connection:
            rows = connection.execute(
                """
                WITH latest AS (
                    SELECT
                        symbol,
                        exchange,
                        interval,
                        timestamp_utc,
                        close,
                        adjusted_close,
                        volume,
                        loaded_at,
                        ROW_NUMBER() OVER (
                            PARTITION BY symbol, exchange, interval
                            ORDER BY timestamp_utc DESC
                        ) AS rank
                    FROM market_bars
                )
                SELECT
                    bars.symbol,
                    bars.exchange,
                    bars.interval,
                    COUNT(*) AS bar_count,
                    MIN(bars.timestamp_utc) AS first_timestamp_utc,
                    MAX(bars.timestamp_utc) AS last_timestamp_utc,
                    MAX(bars.loaded_at) AS last_loaded_at,
                    latest.close AS latest_close,
                    latest.adjusted_close AS latest_adjusted_close,
                    latest.volume AS latest_volume
                FROM market_bars AS bars
                JOIN latest
                  ON latest.symbol = bars.symbol
                 AND latest.exchange = bars.exchange
                 AND latest.interval = bars.interval
                 AND latest.rank = 1
                GROUP BY
                    bars.symbol,
                    bars.exchange,
                    bars.interval,
                    latest.close,
                    latest.adjusted_close,
                    latest.volume
                ORDER BY bars.symbol, bars.exchange, bars.interval
                """
            ).fetchall()
        return [
            {
                "symbol": str(row[0]),
                "exchange": str(row[1]) or None,
                "interval": str(row[2]),
                "bar_count": int(row[3]),
                "first_timestamp_utc": str(row[4]),
                "last_timestamp_utc": str(row[5]),
                "last_loaded_at": str(row[6]),
                "latest_close": float(row[7]),
                "latest_adjusted_close": float(row[8]) if row[8] is not None else None,
                "latest_volume": float(row[9]) if row[9] is not None else None,
            }
            for row in rows
        ]

    def iter_rows(
        self,
        *,
        intervals: set[MarketDataInterval] | None = None,
    ) -> list[dict[str, Any]]:
        parameters: list[str] = []
        where = ""
        if intervals:
            values = sorted(interval.value for interval in intervals)
            where = f"WHERE interval IN ({', '.join('?' for _ in values)})"
            parameters.extend(values)
        with sqlite3.connect(self.db_path) as connection:
            rows = connection.execute(
                f"""
                SELECT
                    symbol,
                    exchange,
                    interval,
                    timestamp_utc,
                    open,
                    high,
                    low,
                    close,
                    adjusted_close,
                    volume,
                    source_name,
                    loaded_at,
                    record_environment
                FROM market_bars
                {where}
                """,
                parameters,
            ).fetchall()
        return [self._bar_from_row(row).model_dump(mode="json") for row in rows]

    def delete_rows(
        self,
        *,
        keys: list[tuple[str, str, str, str]],
    ) -> int:
        if not keys:
            return 0
        deleted = 0
        with sqlite3.connect(self.db_path) as connection:
            for symbol, exchange, interval, timestamp_utc in keys:
                cursor = connection.execute(
                    """
                    DELETE FROM market_bars
                    WHERE symbol = ?
                      AND exchange = ?
                      AND interval = ?
                      AND timestamp_utc = ?
                    """,
                    (symbol, exchange, interval, timestamp_utc),
                )
                deleted += cursor.rowcount
        return deleted

    def _initialise(self) -> None:
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS market_bars (
                    symbol TEXT NOT NULL,
                    exchange TEXT NOT NULL DEFAULT '',
                    interval TEXT NOT NULL,
                    timestamp_utc TEXT NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    adjusted_close REAL,
                    volume REAL,
                    source_name TEXT NOT NULL,
                    loaded_at TEXT NOT NULL,
                    record_environment TEXT NOT NULL,
                    PRIMARY KEY(symbol, exchange, interval, timestamp_utc)
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_market_bars_lookup
                ON market_bars(symbol, exchange, interval, timestamp_utc)
                """
            )

    def _bar_from_row(self, row: tuple[Any, ...]) -> MarketDataBar:
        exchange = str(row[1]) or None
        return MarketDataBar(
            symbol=str(row[0]),
            exchange=exchange,
            interval=MarketDataInterval(str(row[2])),
            timestamp_utc=datetime.fromisoformat(str(row[3])),
            open=float(row[4]),
            high=float(row[5]),
            low=float(row[6]),
            close=float(row[7]),
            adjusted_close=float(row[8]) if row[8] is not None else None,
            volume=float(row[9]) if row[9] is not None else None,
            source_name=str(row[10]),
            loaded_at=datetime.fromisoformat(str(row[11])),
            record_environment=str(row[12]),
        )

    def _exchange_key(self, exchange: str | None) -> str:
        return exchange.upper() if exchange else ""


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
        self.final_outputs = JsonRecordRepository(db_path, "final_outputs")
        self.market_bars = MarketBarRepository(db_path)
        self.market_data_requests = JsonRecordRepository(db_path, "market_data_requests")
        self.event_outcomes = JsonRecordRepository(db_path, "event_outcomes")
        self.calibration_profiles = JsonRecordRepository(db_path, "calibration_profiles")

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
            "final_outputs": self.final_outputs,
            "market_data_requests": self.market_data_requests,
            "event_outcomes": self.event_outcomes,
            "calibration_profiles": self.calibration_profiles,
        }

    def _is_development_or_test_record(self, payload: dict[str, Any]) -> bool:
        environment = payload.get("record_environment")
        if environment == "production":
            return False
        return environment in {"development", "test", None}
