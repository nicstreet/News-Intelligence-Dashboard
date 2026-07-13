from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from news_intelligence.calibration.outcomes import JoinedOutcomeAnalysisService
from news_intelligence.market_data.service import MarketDataService
from news_intelligence.models import MarketDataInterval
from news_intelligence.outputs.final_intelligence import FinalIntelligenceOutputService
from news_intelligence.pipeline import NewsIntelligencePipeline
from news_intelligence.progress import progress_store
from news_intelligence.sources.eodhd_news import EodhdNewsConnector
from news_intelligence.sources.scheduler import SourceScheduler
from news_intelligence.sources.service import SourceIngestionService
from news_intelligence.universe import FavouritesUniverseService
from news_intelligence.utils import stable_hash, to_utc


class IntelligenceRefreshService:
    def __init__(self, pipeline: NewsIntelligencePipeline) -> None:
        self._pipeline = pipeline

    def run(
        self,
        *,
        force_sources: bool = False,
        export_delta: bool = True,
        limit: int = 500,
    ) -> dict[str, Any]:
        started_at = self._pipeline.clock()
        run_id = stable_hash(started_at.isoformat(), prefix="int_run_", length=12)
        errors: list[str] = []
        source_run_payloads: list[dict[str, Any]] = []
        market_data_runs: list[dict[str, Any]] = []
        progress_store.start(run_id, reason="intelligence_refresh")

        def progress(updates: dict[str, Any]) -> None:
            progress_store.update(run_id, **updates)

        try:
            source_runs = SourceScheduler(self._pipeline).poll_due(
                force=force_sources,
                progress=progress,
            )
            source_run_payloads = [run.model_dump(mode="json") for run in source_runs]
        except Exception as exc:
            errors.append(f"source_poll: {exc}")

        try:
            market_data_runs = self._refresh_market_data(limit=limit, progress=progress)
        except Exception as exc:
            errors.append(f"market_data: {exc}")

        progress({"phase": "joining_outcomes", "message": "Joining news signals to market data"})
        outcomes = JoinedOutcomeAnalysisService(
            self._pipeline.repositories,
            FavouritesUniverseService(self._pipeline.config),
        ).outcomes(limit=limit)
        output_service = FinalIntelligenceOutputService(
            self._pipeline.config,
            self._pipeline.repositories,
        )
        progress({"phase": "exporting", "message": "Writing changed final JSON records"})
        export_manifest = (
            output_service.export_delta(limit=limit, run_id=run_id) if export_delta else None
        )
        output = output_service.list_output(limit=limit)
        completed_at = self._pipeline.clock()
        payload = {
            "automation_run_id": run_id,
            "reason": "intelligence_refresh",
            "record_environment": self._pipeline.config.environment,
            "started_at": started_at.isoformat(),
            "completed_at": completed_at.isoformat(),
            "source_run_count": len(source_run_payloads),
            "fetched_count": sum(int(run.get("fetched_count", 0)) for run in source_run_payloads),
            "ingested_count": sum(int(run.get("ingested_count", 0)) for run in source_run_payloads),
            "skipped_count": sum(int(run.get("skipped_count", 0)) for run in source_run_payloads),
            "market_data_request_count": len(market_data_runs),
            "market_data_records_stored": sum(
                int(run.get("records_stored", 0)) for run in market_data_runs
            ),
            "outcome_count": outcomes.get("outcome_count", 0),
            "missing_market_data_count": outcomes.get("missing_market_data_count", 0),
            "final_record_count": output.get("record_count", 0),
            "exported_count": (
                int(export_manifest.get("records_exported", 0)) if export_manifest else 0
            ),
            "error_count": len(errors),
            "errors": errors,
            "source_runs": source_run_payloads,
            "market_data_runs": market_data_runs,
            "export_manifest": export_manifest,
            "retention_applied": False,
            "retention_result": None,
        }
        self._pipeline.repositories.automation_runs.save(run_id, payload)
        progress_store.finish(
            run_id,
            status="error" if errors else "complete",
            message=(
                f"{output.get('record_count', 0)} records, "
                f"{payload['exported_count']} exported"
            ),
            fetched_count=payload["fetched_count"],
            ingested_count=payload["ingested_count"],
            skipped_count=payload["skipped_count"],
            exported_count=payload["exported_count"],
            error_count=payload["error_count"],
        )
        return {**payload, "output": output}

    def backfill(
        self,
        *,
        start: date,
        end: date,
        source: str = "eodhd_news",
        export_delta: bool = True,
        limit: int = 5_000,
        page_limit: int | None = None,
        max_pages: int | None = None,
        symbols: list[str] | None = None,
    ) -> dict[str, Any]:
        if end < start:
            raise ValueError("Backfill end date must be on or after the start date.")
        if source != "eodhd_news":
            raise ValueError("Only eodhd_news historical backfill is currently supported.")
        requested_symbols = self._normalise_symbols(symbols)

        started_at = self._pipeline.clock()
        run_id = stable_hash(
            "historical_backfill",
            start.isoformat(),
            end.isoformat(),
            ",".join(requested_symbols),
            started_at.isoformat(),
            prefix="backfill_",
            length=12,
        )
        errors: list[str] = []
        source_run_payloads: list[dict[str, Any]] = []
        market_data_runs: list[dict[str, Any]] = []
        progress_store.start(run_id, reason="historical_backfill")

        def progress(updates: dict[str, Any]) -> None:
            progress_store.update(run_id, **updates)

        connector = EodhdNewsConnector(self._pipeline.config, clock=self._pipeline.clock)
        ingestion = SourceIngestionService(self._pipeline)
        try:
            progress(
                {
                    "phase": "fetching_source",
                    "message": (
                        f"Fetching {connector.source_name} from {start} to {end}"
                        f"{self._symbol_scope_message(requested_symbols)}"
                    ),
                    "connector_name": connector.source_name,
                    "connector_type": connector.connector_type,
                    "connector_index": 1,
                    "connector_total": 1,
                    "symbols": requested_symbols,
                }
            )
            records = connector.fetch_range(
                start=start,
                end=end,
                known_source_record_ids=ingestion.known_source_record_ids(
                    connector.connector_type
                ),
                limit=page_limit,
                max_pages=max_pages,
                symbols=requested_symbols or None,
            )
            source_run = ingestion.ingest_fetched(
                connector,
                records,
                progress=progress,
                connector_index=1,
                connector_total=1,
            )
            source_run_payloads = [source_run.model_dump(mode="json")]
        except Exception as exc:
            errors.append(f"source_backfill: {exc}")

        try:
            market_data_runs = self._refresh_market_data(
                limit=limit,
                start=start,
                end=end,
                symbols=requested_symbols or None,
                progress=progress,
            )
        except Exception as exc:
            errors.append(f"market_data: {exc}")

        progress({"phase": "joining_outcomes", "message": "Joining backfilled news to market data"})
        outcomes = JoinedOutcomeAnalysisService(
            self._pipeline.repositories,
            FavouritesUniverseService(self._pipeline.config),
        ).outcomes(limit=limit)
        output_service = FinalIntelligenceOutputService(
            self._pipeline.config,
            self._pipeline.repositories,
        )
        progress({"phase": "exporting", "message": "Writing historical JSON export"})
        export_manifest = (
            output_service.export_delta(
                limit=limit,
                run_id=run_id,
                start=start,
                end=end,
                symbols=requested_symbols or None,
            )
            if export_delta
            else None
        )
        output = output_service.list_output(
            limit=limit,
            start=start,
            end=end,
            symbols=requested_symbols or None,
        )
        completed_at = self._pipeline.clock()
        payload = {
            "automation_run_id": run_id,
            "reason": "historical_backfill",
            "record_environment": self._pipeline.config.environment,
            "date_range": {"from": start.isoformat(), "to": end.isoformat()},
            "source": source,
            "symbols": requested_symbols,
            "started_at": started_at.isoformat(),
            "completed_at": completed_at.isoformat(),
            "source_run_count": len(source_run_payloads),
            "fetched_count": sum(int(run.get("fetched_count", 0)) for run in source_run_payloads),
            "ingested_count": sum(
                int(run.get("ingested_count", 0)) for run in source_run_payloads
            ),
            "skipped_count": sum(
                int(run.get("skipped_count", 0)) for run in source_run_payloads
            ),
            "market_data_request_count": len(market_data_runs),
            "market_data_records_stored": sum(
                int(run.get("records_stored", 0)) for run in market_data_runs
            ),
            "outcome_count": outcomes.get("outcome_count", 0),
            "missing_market_data_count": outcomes.get("missing_market_data_count", 0),
            "final_record_count": output.get("record_count", 0),
            "exported_count": (
                int(export_manifest.get("records_exported", 0)) if export_manifest else 0
            ),
            "error_count": len(errors),
            "errors": errors,
            "source_runs": source_run_payloads,
            "market_data_runs": market_data_runs,
            "export_manifest": export_manifest,
            "retention_applied": False,
            "retention_result": None,
        }
        self._pipeline.repositories.automation_runs.save(run_id, payload)
        progress_store.finish(
            run_id,
            status="error" if errors else "complete",
            message=(
                f"{output.get('record_count', 0)} historical records, "
                f"{payload['exported_count']} exported"
            ),
            fetched_count=payload["fetched_count"],
            ingested_count=payload["ingested_count"],
            skipped_count=payload["skipped_count"],
            exported_count=payload["exported_count"],
            error_count=payload["error_count"],
        )
        return {**payload, "output": output}

    def _refresh_market_data(
        self,
        *,
        limit: int,
        start: date | None = None,
        end: date | None = None,
        symbols: list[str] | None = None,
        progress: Any | None = None,
    ) -> list[dict[str, Any]]:
        settings = self._market_data_settings()
        if not settings.get("enabled", True):
            return []
        if not self._pipeline.config.eodhd_api_token:
            return []
        max_symbols = max(0, int(settings.get("max_symbols_per_run", 12)))
        lookback_days = max(1, int(settings.get("lookback_days", 40)))
        results: list[dict[str, Any]] = []
        service = MarketDataService(
            self._pipeline.config,
            self._pipeline.repositories,
            clock=self._pipeline.clock,
        )
        today = self._pipeline.clock().date()
        if start is not None and end is not None:
            request_start = start - timedelta(days=1)
            request_end = min(today, end + timedelta(days=35))
            if request_start > request_end:
                return []
            candidates = self._symbols_in_event_window(
                start=start,
                end=end,
                limit=limit,
                symbols=symbols,
            )[:max_symbols]
            for index, candidate in enumerate(candidates, start=1):
                self._progress(
                    progress,
                    phase="fetching_market_data",
                    message=f"Fetching EODHD daily bars for {candidate['symbol']}",
                    market_symbol=candidate["symbol"],
                    market_symbol_index=index,
                    market_symbol_total=len(candidates),
                )
                if self._has_daily_bar_coverage(
                    symbol=candidate["symbol"],
                    exchange=candidate["exchange"],
                    start=request_start,
                    end=request_end,
                ):
                    continue
                results.append(
                    service.fetch_daily(
                        symbol=candidate["symbol"],
                        exchange=candidate["exchange"],
                        start=request_start,
                        end=request_end,
                    )
                )
            return results

        required_symbols = self._symbols_requiring_market_data(limit=limit)
        candidates = required_symbols[:max_symbols]
        for index, candidate in enumerate(candidates, start=1):
            self._progress(
                progress,
                phase="fetching_market_data",
                message=f"Fetching EODHD daily bars for {candidate['symbol']}",
                market_symbol=candidate["symbol"],
                market_symbol_index=index,
                market_symbol_total=len(candidates),
            )
            start = max(
                candidate["event_date"] - timedelta(days=1),
                today - timedelta(days=lookback_days),
            )
            end = min(today, candidate["event_date"] + timedelta(days=30))
            if start > end:
                continue
            if self._has_daily_bars(
                symbol=candidate["symbol"],
                exchange=candidate["exchange"],
                start=start,
                end=end,
            ):
                continue
            results.append(
                service.fetch_daily(
                    symbol=candidate["symbol"],
                    exchange=candidate["exchange"],
                    start=start,
                    end=end,
                )
            )
        return results

    def _progress(self, progress: Any | None, **updates: Any) -> None:
        if progress is not None:
            progress(updates)

    def _symbols_in_event_window(
        self,
        *,
        start: date,
        end: date,
        limit: int,
        symbols: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        universe = FavouritesUniverseService(self._pipeline.config).universe()
        instruments = {instrument.symbol.upper(): instrument for instrument in universe.instruments}
        symbol_filter = set(self._normalise_symbols(symbols))
        events = {
            str(event.get("event_id", "")): event
            for event in self._pipeline.repositories.events.list_recent(limit)
        }
        candidates: dict[tuple[str, str], dict[str, Any]] = {}
        for signal in self._pipeline.repositories.signals.list_recent(limit):
            instrument_payload = signal.get("instrument", {})
            if not isinstance(instrument_payload, dict):
                continue
            symbol = str(instrument_payload.get("symbol", "")).upper()
            event = events.get(str(signal.get("event_id", "")))
            event_at = self._event_time(event, signal)
            if not symbol or event_at is None:
                continue
            if symbol_filter and symbol not in symbol_filter:
                event_symbols = self._event_symbols(event)
                if not event_symbols.intersection(symbol_filter):
                    continue
            event_date = to_utc(event_at).date()
            if event_date < start or event_date > end:
                continue
            instrument = instruments.get(symbol)
            exchange = str(
                instrument_payload.get("exchange")
                or (instrument.exchange if instrument else "")
            ).upper() or None
            self._add_candidate(candidates, symbol=symbol, exchange=exchange, event_at=event_at)
            benchmark = instrument.benchmark if instrument else None
            if benchmark:
                benchmark_instrument = instruments.get(benchmark.upper())
                benchmark_exchange = (
                    benchmark_instrument.exchange if benchmark_instrument else exchange
                )
                self._add_candidate(
                    candidates,
                    symbol=benchmark,
                    exchange=benchmark_exchange,
                    event_at=event_at,
                )
        return sorted(candidates.values(), key=lambda candidate: candidate["symbol"])

    def _normalise_symbols(self, symbols: list[str] | None) -> list[str]:
        seen: set[str] = set()
        normalised: list[str] = []
        for symbol in symbols or []:
            clean = str(symbol).strip().upper()
            if clean and clean not in seen:
                seen.add(clean)
                normalised.append(clean)
        return normalised

    def _symbol_scope_message(self, symbols: list[str]) -> str:
        if not symbols:
            return ""
        sample = ", ".join(symbols[:5])
        suffix = "" if len(symbols) <= 5 else f" +{len(symbols) - 5}"
        return f" for {len(symbols)} symbol(s): {sample}{suffix}"

    def _event_symbols(self, event: dict[str, Any] | None) -> set[str]:
        if not isinstance(event, dict):
            return set()
        symbols: set[str] = set()
        primary = str(event.get("primary_symbol", "")).strip().upper()
        if primary:
            symbols.add(primary)
        entities = event.get("entities")
        if isinstance(entities, list):
            for entity in entities:
                if not isinstance(entity, dict):
                    continue
                symbol = str(entity.get("symbol", "")).strip().upper()
                if symbol:
                    symbols.add(symbol)
        return symbols

    def _symbols_requiring_market_data(self, *, limit: int) -> list[dict[str, Any]]:
        universe = FavouritesUniverseService(self._pipeline.config).universe()
        instruments = {instrument.symbol.upper(): instrument for instrument in universe.instruments}
        events = {
            str(event.get("event_id", "")): event
            for event in self._pipeline.repositories.events.list_recent(limit)
        }
        candidates: dict[tuple[str, str], dict[str, Any]] = {}
        for signal in self._pipeline.repositories.signals.list_recent(limit):
            instrument_payload = signal.get("instrument", {})
            if not isinstance(instrument_payload, dict):
                continue
            symbol = str(instrument_payload.get("symbol", "")).upper()
            event = events.get(str(signal.get("event_id", "")))
            event_at = self._event_time(event, signal)
            if not symbol or event_at is None:
                continue
            instrument = instruments.get(symbol)
            exchange = str(
                instrument_payload.get("exchange")
                or (instrument.exchange if instrument else "")
            ).upper() or None
            self._add_candidate(candidates, symbol=symbol, exchange=exchange, event_at=event_at)
            benchmark = instrument.benchmark if instrument else None
            if benchmark:
                benchmark_instrument = instruments.get(benchmark.upper())
                benchmark_exchange = (
                    benchmark_instrument.exchange if benchmark_instrument else exchange
                )
                self._add_candidate(
                    candidates,
                    symbol=benchmark,
                    exchange=benchmark_exchange,
                    event_at=event_at,
                )
        return sorted(
            candidates.values(),
            key=lambda candidate: candidate["event_date"],
            reverse=True,
        )

    def _add_candidate(
        self,
        candidates: dict[tuple[str, str], dict[str, Any]],
        *,
        symbol: str,
        exchange: str | None,
        event_at: datetime,
    ) -> None:
        key = (symbol.upper(), (exchange or "").upper())
        existing = candidates.get(key)
        event_date = to_utc(event_at).date()
        if existing is None or event_date > existing["event_date"]:
            candidates[key] = {
                "symbol": symbol.upper(),
                "exchange": exchange.upper() if exchange else None,
                "event_date": event_date,
            }

    def _has_daily_bars(
        self,
        *,
        symbol: str,
        exchange: str | None,
        start: date,
        end: date,
    ) -> bool:
        bars = self._pipeline.repositories.market_bars.list_range(
            symbol=symbol,
            exchange=exchange,
            interval=MarketDataInterval.DAILY,
            start_at=datetime.combine(start, datetime.min.time(), tzinfo=UTC),
            end_at=datetime.combine(end, datetime.min.time(), tzinfo=UTC),
        )
        return bool(bars)

    def _has_daily_bar_coverage(
        self,
        *,
        symbol: str,
        exchange: str | None,
        start: date,
        end: date,
    ) -> bool:
        bars = self._pipeline.repositories.market_bars.list_range(
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

    def _event_time(
        self,
        event: dict[str, Any] | None,
        signal: dict[str, Any],
    ) -> datetime | None:
        timestamps = event.get("timestamps", {}) if isinstance(event, dict) else {}
        if isinstance(timestamps, dict):
            for key in ("published_at", "processed_at"):
                parsed = self._parse_datetime(timestamps.get(key))
                if parsed is not None:
                    return parsed
        return self._parse_datetime(signal.get("generated_at"))

    def _parse_datetime(self, value: Any) -> datetime | None:
        if not isinstance(value, str):
            return None
        try:
            return to_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
        except ValueError:
            return None

    def _market_data_settings(self) -> dict[str, Any]:
        settings = self._pipeline.config.automation.get("market_data", {})
        return settings if isinstance(settings, dict) else {}
