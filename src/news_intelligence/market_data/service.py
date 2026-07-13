from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any

from news_intelligence.config import NewsIntelligenceConfig
from news_intelligence.market_data.eodhd import EodhdMarketDataClient
from news_intelligence.models import MarketDataInterval, MarketDataRequest, RuntimeEnvironment
from news_intelligence.storage import RepositoryBundle
from news_intelligence.universe import FavouritesUniverseService
from news_intelligence.utils import stable_hash, to_utc


class MarketDataService:
    def __init__(
        self,
        config: NewsIntelligenceConfig,
        repositories: RepositoryBundle,
        *,
        client: EodhdMarketDataClient | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._config = config
        self._repositories = repositories
        self._clock = clock or (lambda: datetime.now(UTC))
        self._client = client or EodhdMarketDataClient(config, clock=self._clock)

    def fetch_daily(
        self,
        *,
        symbol: str,
        exchange: str | None,
        start: date,
        end: date,
    ) -> dict[str, Any]:
        requested_at = self._clock()
        request_id = self._request_id(
            endpoint="eod",
            symbol=symbol,
            exchange=exchange,
            interval=MarketDataInterval.DAILY,
            requested_from=datetime.combine(start, datetime.min.time(), tzinfo=UTC),
            requested_to=datetime.combine(end, datetime.min.time(), tzinfo=UTC),
        )
        try:
            bars = self._client.fetch_daily_bars(
                symbol=symbol,
                exchange=exchange,
                start=start,
                end=end,
            )
            stored = self._repositories.market_bars.save_many(bars)
            request = MarketDataRequest(
                request_id=request_id,
                endpoint="eod",
                symbol=symbol,
                exchange=exchange,
                interval=MarketDataInterval.DAILY,
                requested_from=datetime.combine(start, datetime.min.time(), tzinfo=UTC),
                requested_to=datetime.combine(end, datetime.min.time(), tzinfo=UTC),
                requested_at=requested_at,
                completed_at=self._clock(),
                status="success",
                records_returned=len(bars),
                records_stored=stored,
                estimated_api_call_cost=self._client.estimated_call_cost(
                    MarketDataInterval.DAILY
                ),
                record_environment=self._record_environment(),
            )
        except Exception as exc:
            request = MarketDataRequest(
                request_id=request_id,
                endpoint="eod",
                symbol=symbol,
                exchange=exchange,
                interval=MarketDataInterval.DAILY,
                requested_from=datetime.combine(start, datetime.min.time(), tzinfo=UTC),
                requested_to=datetime.combine(end, datetime.min.time(), tzinfo=UTC),
                requested_at=requested_at,
                completed_at=self._clock(),
                status="failed",
                records_returned=0,
                records_stored=0,
                estimated_api_call_cost=self._client.estimated_call_cost(
                    MarketDataInterval.DAILY
                ),
                error=str(exc),
                record_environment=self._record_environment(),
            )
            self._repositories.market_data_requests.save(request_id, request)
            raise
        self._repositories.market_data_requests.save(request_id, request)
        return self._fetch_payload(request)

    def fetch_intraday(
        self,
        *,
        symbol: str,
        exchange: str | None,
        interval: MarketDataInterval,
        start_at: datetime,
        end_at: datetime,
    ) -> dict[str, Any]:
        requested_at = self._clock()
        request_id = self._request_id(
            endpoint="intraday",
            symbol=symbol,
            exchange=exchange,
            interval=interval,
            requested_from=to_utc(start_at),
            requested_to=to_utc(end_at),
        )
        try:
            bars = self._client.fetch_intraday_bars(
                symbol=symbol,
                exchange=exchange,
                interval=interval,
                start_at=start_at,
                end_at=end_at,
            )
            stored = self._repositories.market_bars.save_many(bars)
            request = MarketDataRequest(
                request_id=request_id,
                endpoint="intraday",
                symbol=symbol,
                exchange=exchange,
                interval=interval,
                requested_from=start_at,
                requested_to=end_at,
                requested_at=requested_at,
                completed_at=self._clock(),
                status="success",
                records_returned=len(bars),
                records_stored=stored,
                estimated_api_call_cost=self._client.estimated_call_cost(interval),
                record_environment=self._record_environment(),
            )
        except Exception as exc:
            request = MarketDataRequest(
                request_id=request_id,
                endpoint="intraday",
                symbol=symbol,
                exchange=exchange,
                interval=interval,
                requested_from=start_at,
                requested_to=end_at,
                requested_at=requested_at,
                completed_at=self._clock(),
                status="failed",
                records_returned=0,
                records_stored=0,
                estimated_api_call_cost=self._client.estimated_call_cost(interval),
                error=str(exc),
                record_environment=self._record_environment(),
            )
            self._repositories.market_data_requests.save(request_id, request)
            raise
        self._repositories.market_data_requests.save(request_id, request)
        return self._fetch_payload(request)

    def recent_requests(self, limit: int = 50) -> list[dict[str, Any]]:
        return self._repositories.market_data_requests.list_recent(limit)

    def recent_bars(self, limit: int = 50) -> list[dict[str, Any]]:
        return self._repositories.market_bars.list_recent(limit)

    def coverage_summary(self) -> dict[str, Any]:
        rows = self._repositories.market_bars.coverage_summary()
        latest_requests = self._latest_requests_by_market_key()
        enriched_rows: list[dict[str, Any]] = []
        for row in rows:
            key = self._market_key(
                symbol=str(row["symbol"]),
                exchange=row.get("exchange"),
                interval=str(row["interval"]),
            )
            request = latest_requests.get(key, {})
            enriched_rows.append(
                {
                    **row,
                    "last_request_status": request.get("status"),
                    "last_request_at": request.get("completed_at")
                    or request.get("requested_at"),
                    "last_request_from": request.get("requested_from"),
                    "last_request_to": request.get("requested_to"),
                    "last_request_error": request.get("error"),
                }
            )
        configured_symbols = self._configured_symbols()
        covered_symbols = {str(row["symbol"]).upper() for row in enriched_rows}
        missing_symbols = sorted(configured_symbols - covered_symbols)
        return {
            "schema_version": "1.0.0",
            "provider": "EODHD",
            "record_count": len(enriched_rows),
            "covered_symbol_count": len(covered_symbols),
            "configured_symbol_count": len(configured_symbols),
            "missing_configured_symbols": missing_symbols,
            "total_bar_count": sum(int(row.get("bar_count", 0)) for row in enriched_rows),
            "first_timestamp_utc": min(
                (str(row["first_timestamp_utc"]) for row in enriched_rows),
                default=None,
            ),
            "last_timestamp_utc": max(
                (str(row["last_timestamp_utc"]) for row in enriched_rows),
                default=None,
            ),
            "rows": enriched_rows,
        }

    def mapping_summary(self, recent_limit: int = 200) -> dict[str, Any]:
        exchange_suffixes = self._string_mapping("exchange_suffixes")
        symbol_overrides = self._string_mapping("symbol_overrides")
        return {
            "schema_version": "1.0.0",
            "provider": "EODHD",
            "mapping_file": "config/eodhd.yaml",
            "exchange_suffixes": [
                {"exchange": exchange, "provider_suffix": suffix}
                for exchange, suffix in sorted(exchange_suffixes.items())
            ],
            "symbol_overrides": [
                {
                    "symbol": symbol,
                    "provider_symbol": provider_symbol,
                    "mapping_type": "provider_override",
                }
                for symbol, provider_symbol in sorted(symbol_overrides.items())
            ],
            "recent_failures": self._recent_mapping_failures(
                recent_limit=recent_limit,
                symbol_overrides=symbol_overrides,
                exchange_suffixes=exchange_suffixes,
            ),
        }

    def _fetch_payload(self, request: MarketDataRequest) -> dict[str, Any]:
        return {
            **request.model_dump(mode="json"),
            "token_redacted": True,
        }

    def _latest_requests_by_market_key(self) -> dict[tuple[str, str, str], dict[str, Any]]:
        latest: dict[tuple[str, str, str], dict[str, Any]] = {}
        for request in self._repositories.market_data_requests.list_all():
            key = self._market_key(
                symbol=str(request.get("symbol", "")),
                exchange=request.get("exchange"),
                interval=str(request.get("interval", "")),
            )
            current = latest.get(key)
            request_time = str(request.get("completed_at") or request.get("requested_at") or "")
            current_time = (
                str(current.get("completed_at") or current.get("requested_at") or "")
                if current
                else ""
            )
            if current is None or request_time >= current_time:
                latest[key] = request
        return latest

    def _configured_symbols(self) -> set[str]:
        universe = FavouritesUniverseService(self._config).universe()
        symbols = {instrument.symbol.upper() for instrument in universe.instruments}
        symbols.update(
            instrument.benchmark.upper()
            for instrument in universe.instruments
            if instrument.benchmark
        )
        default_benchmarks = universe.default_benchmarks or {}
        symbols.update(
            str(symbol).upper()
            for symbol in default_benchmarks.values()
            if symbol
        )
        return symbols

    def _market_key(
        self,
        *,
        symbol: str,
        exchange: str | None,
        interval: str,
    ) -> tuple[str, str, str]:
        return (
            symbol.upper(),
            str(exchange or "").upper(),
            interval,
        )

    def _recent_mapping_failures(
        self,
        *,
        recent_limit: int,
        symbol_overrides: dict[str, str],
        exchange_suffixes: dict[str, str],
    ) -> list[dict[str, Any]]:
        failures: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        for request in self._repositories.market_data_requests.list_recent(recent_limit):
            if request.get("status") != "failed":
                continue
            symbol = str(request.get("symbol", "")).upper()
            exchange = str(request.get("exchange") or "").upper()
            interval = str(request.get("interval", ""))
            if not symbol:
                continue
            key = (symbol, exchange, interval)
            if key in seen:
                continue
            seen.add(key)
            provider_symbol = self._client.eodhd_symbol(symbol, exchange or None)
            error = str(request.get("error") or "")
            failures.append(
                {
                    "symbol": symbol,
                    "exchange": exchange or None,
                    "interval": interval,
                    "requested_at": request.get("requested_at"),
                    "current_provider_symbol": provider_symbol,
                    "failure_kind": "provider_not_found"
                    if "HTTP 404" in error
                    else "request_failed",
                    "mapping_status": self._mapping_status(
                        symbol=symbol,
                        exchange=exchange,
                        symbol_overrides=symbol_overrides,
                        exchange_suffixes=exchange_suffixes,
                    ),
                    "error": error or None,
                }
            )
        return failures

    def _mapping_status(
        self,
        *,
        symbol: str,
        exchange: str,
        symbol_overrides: dict[str, str],
        exchange_suffixes: dict[str, str],
    ) -> str:
        if symbol in symbol_overrides:
            return "provider_override"
        if "." in symbol:
            return "embedded_provider_suffix"
        if exchange and exchange in exchange_suffixes:
            return "exchange_suffix"
        return "default_us_suffix"

    def _string_mapping(self, key: str) -> dict[str, str]:
        value = self._config.eodhd.get(key, {})
        if not isinstance(value, dict):
            return {}
        return {str(name).upper(): str(mapped).upper() for name, mapped in value.items()}

    def _request_id(
        self,
        *,
        endpoint: str,
        symbol: str,
        exchange: str | None,
        interval: MarketDataInterval,
        requested_from: datetime,
        requested_to: datetime,
    ) -> str:
        return stable_hash(
            "eodhd",
            endpoint,
            symbol.upper(),
            exchange.upper() if exchange else "",
            interval.value,
            to_utc(requested_from).isoformat(),
            to_utc(requested_to).isoformat(),
            prefix="mreq_",
            length=16,
        )

    def _record_environment(self) -> RuntimeEnvironment:
        try:
            return RuntimeEnvironment(self._config.environment)
        except ValueError:
            return RuntimeEnvironment.DEVELOPMENT
