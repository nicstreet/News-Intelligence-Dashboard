from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

from news_intelligence.config import NewsIntelligenceConfig
from news_intelligence.market_data.service import MarketDataService
from news_intelligence.models import MarketDataInterval
from news_intelligence.progress import progress_store
from news_intelligence.storage import RepositoryBundle
from news_intelligence.universe import FavouritesUniverseService
from news_intelligence.utils import stable_hash


class MarketDataHistoryBackfillService:
    def __init__(
        self,
        config: NewsIntelligenceConfig,
        repositories: RepositoryBundle,
        *,
        clock: Callable[[], datetime] | None = None,
        market_data_service: MarketDataService | None = None,
    ) -> None:
        self._config = config
        self._repositories = repositories
        self._clock = clock or (lambda: datetime.now(UTC))
        self._service = market_data_service or MarketDataService(
            config,
            repositories,
            clock=self._clock,
        )

    def populate_daily_history(
        self,
        *,
        start: date,
        end: date,
        include_benchmarks: bool = True,
        symbols: list[str] | None = None,
        max_symbols: int | None = None,
    ) -> dict[str, Any]:
        if end < start:
            raise ValueError("Market-data end date must be on or after the start date.")
        run_id = stable_hash(
            "market_data_history",
            start.isoformat(),
            end.isoformat(),
            self._clock().isoformat(),
            prefix="mkt_hist_",
            length=12,
        )
        progress_store.start(run_id, reason="market_data_history")
        candidates = self._candidates(
            include_benchmarks=include_benchmarks,
            symbols=symbols,
        )
        if max_symbols is not None:
            candidates = candidates[: max(0, int(max_symbols))]
        results: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        total = len(candidates)
        for index, candidate in enumerate(candidates, start=1):
            symbol = str(candidate["symbol"]).upper()
            exchange = candidate.get("exchange")
            progress_store.update(
                run_id,
                status="running",
                phase="fetching_market_data",
                message=f"Fetching EODHD daily bars for {symbol}",
                market_symbol=symbol,
                market_symbol_index=index,
                market_symbol_total=total,
                record_index=index,
                record_total=total,
                ingested_count=sum(int(item.get("records_stored", 0)) for item in results),
                skipped_count=len(skipped),
                error_count=len(errors),
            )
            if self._has_coverage(
                symbol=symbol,
                exchange=str(exchange).upper() if exchange else None,
                start=start,
                end=end,
            ):
                skipped.append(
                    {
                        "symbol": symbol,
                        "exchange": exchange,
                        "reason": "coverage_already_cached",
                    }
                )
                continue
            try:
                results.append(
                    self._service.fetch_daily(
                        symbol=symbol,
                        exchange=str(exchange).upper() if exchange else None,
                        start=start,
                        end=end,
                    )
                )
            except Exception as exc:
                errors.append({"symbol": symbol, "exchange": exchange, "error": str(exc)})

        records_stored = sum(int(item.get("records_stored", 0)) for item in results)
        payload = {
            "automation_run_id": run_id,
            "reason": "market_data_history",
            "record_environment": self._config.environment,
            "date_range": {"from": start.isoformat(), "to": end.isoformat()},
            "symbol_count": total,
            "request_count": len(results),
            "skipped_count": len(skipped),
            "error_count": len(errors),
            "records_stored": records_stored,
            "estimated_api_call_cost": sum(
                int(item.get("estimated_api_call_cost", 0)) for item in results
            ),
            "results": results,
            "skipped": skipped,
            "errors": errors,
            "completed_at": self._clock().isoformat(),
        }
        self._repositories.automation_runs.save(run_id, payload)
        progress_store.finish(
            run_id,
            status="error" if errors else "complete",
            message=f"{records_stored} market bars stored for {total} symbols",
            market_symbol=None,
            market_symbol_index=total,
            market_symbol_total=total,
            record_index=total,
            record_total=total,
            ingested_count=records_stored,
            skipped_count=len(skipped),
            error_count=len(errors),
        )
        return payload

    def _candidates(
        self,
        *,
        include_benchmarks: bool,
        symbols: list[str] | None,
    ) -> list[dict[str, str | None]]:
        universe = FavouritesUniverseService(self._config).universe()
        instruments = {instrument.symbol.upper(): instrument for instrument in universe.instruments}
        requested = {symbol.upper() for symbol in symbols or [] if symbol}
        candidates: dict[tuple[str, str], dict[str, str | None]] = {}
        if requested:
            for symbol in sorted(requested):
                instrument = instruments.get(symbol)
                self._add_candidate(
                    candidates,
                    symbol=symbol,
                    exchange=instrument.exchange if instrument else None,
                )
                if include_benchmarks and instrument and instrument.benchmark:
                    self._add_candidate(
                        candidates,
                        symbol=instrument.benchmark.upper(),
                        exchange=self._instrument_exchange(
                            instruments=instruments,
                            symbol=instrument.benchmark,
                        ),
                    )
            return sorted(candidates.values(), key=lambda item: str(item["symbol"]))

        for instrument in universe.instruments:
            symbol = instrument.symbol.upper()
            self._add_candidate(candidates, symbol=symbol, exchange=instrument.exchange)
            if include_benchmarks and instrument.benchmark:
                self._add_candidate(
                    candidates,
                    symbol=instrument.benchmark.upper(),
                    exchange=self._instrument_exchange(
                        instruments=instruments,
                        symbol=instrument.benchmark,
                    ),
                )
        if include_benchmarks:
            for benchmark in (universe.default_benchmarks or {}).values():
                if benchmark:
                    self._add_candidate(
                        candidates,
                        symbol=str(benchmark).upper(),
                        exchange=self._instrument_exchange(
                            instruments=instruments,
                            symbol=str(benchmark),
                        ),
                    )
        return sorted(candidates.values(), key=lambda item: str(item["symbol"]))

    def _instrument_exchange(
        self,
        *,
        instruments: dict[str, Any],
        symbol: str,
    ) -> str | None:
        instrument = instruments.get(symbol.upper())
        return instrument.exchange if instrument else None

    def _add_candidate(
        self,
        candidates: dict[tuple[str, str], dict[str, str | None]],
        *,
        symbol: str,
        exchange: str | None,
    ) -> None:
        key = (symbol.upper(), (exchange or "").upper())
        candidates[key] = {
            "symbol": symbol.upper(),
            "exchange": exchange.upper() if exchange else None,
        }

    def _has_coverage(
        self,
        *,
        symbol: str,
        exchange: str | None,
        start: date,
        end: date,
    ) -> bool:
        bars = self._repositories.market_bars.list_range(
            symbol=symbol,
            exchange=exchange,
            interval=MarketDataInterval.DAILY,
            start_at=datetime.combine(start, datetime.min.time(), tzinfo=UTC),
            end_at=datetime.combine(end, datetime.min.time(), tzinfo=UTC),
        )
        if not bars:
            return False
        first = min(bar.timestamp_utc.date() for bar in bars)
        last = max(bar.timestamp_utc.date() for bar in bars)
        return first <= start + timedelta(days=3) and last >= end - timedelta(days=3)
