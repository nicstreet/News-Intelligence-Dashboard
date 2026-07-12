from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from statistics import median
from typing import Any

from news_intelligence.market_data.timing import EventMarketTimer
from news_intelligence.models import MarketDataBar, MarketDataInterval
from news_intelligence.storage import RepositoryBundle
from news_intelligence.universe import FavouritesUniverseService
from news_intelligence.utils import now_utc, to_utc

INTRADAY_INTERVALS = (
    MarketDataInterval.ONE_MINUTE,
    MarketDataInterval.FIVE_MINUTE,
    MarketDataInterval.ONE_HOUR,
)

INTRADAY_WINDOWS = {
    "30m": timedelta(minutes=30),
    "1h": timedelta(hours=1),
}

DAILY_WINDOWS = {
    "1d": 1,
    "3d": 3,
    "5d": 5,
    "20d": 20,
}


@dataclass(frozen=True)
class _SymbolOutcome:
    symbol: str
    exchange: str | None
    price_at_event: float | None
    price_source: str | None
    market_anchor_at: datetime
    anchor_source: str
    market_session: str
    returns: dict[str, float | None]
    maximum_favourable_excursion_5d: float | None
    maximum_adverse_excursion_5d: float | None
    bars_available: dict[str, int]
    notes: list[str]


class JoinedOutcomeAnalysisService:
    """Builds a read-only news-signal vs cached market-data outcome view."""

    def __init__(
        self,
        repositories: RepositoryBundle,
        universe: FavouritesUniverseService,
    ) -> None:
        self._repositories = repositories
        self._universe = universe
        self._timer = EventMarketTimer()
        self._instruments = {
            instrument.symbol.upper(): instrument
            for instrument in self._universe.universe().instruments
        }

    def outcomes(self, *, limit: int = 500) -> dict[str, Any]:
        events = self._repositories.events.list_recent(limit)
        signals = self._repositories.signals.list_recent(limit)
        events_by_id = {str(event.get("event_id", "")): event for event in events}

        rows: list[dict[str, Any]] = []
        for signal in signals:
            event = events_by_id.get(str(signal.get("event_id", "")))
            if event is None:
                continue
            symbol = self._signal_symbol(signal)
            if symbol not in self._instruments:
                continue
            event_at = self._event_time(event, signal)
            if event_at is None:
                continue
            rows.append(self._outcome_row(event=event, signal=signal, event_at=event_at))

        profile_summaries = self._profile_summaries(rows)
        missing_count = sum(1 for row in rows if row["outcome_status"] == "missing_market_data")
        usable_count = sum(1 for row in rows if row["outcome_status"] != "missing_market_data")
        return {
            "schema_version": "1.0.0",
            "generated_at": now_utc().isoformat(),
            "universe_version": self._universe.universe().version,
            "signal_count": len(rows),
            "outcome_count": usable_count,
            "missing_market_data_count": missing_count,
            "outcome_status": "ready" if usable_count else "pending_market_data_join",
            "profiles": profile_summaries,
            "rows": rows,
        }

    def _outcome_row(
        self,
        *,
        event: dict[str, Any],
        signal: dict[str, Any],
        event_at: datetime,
    ) -> dict[str, Any]:
        symbol = self._signal_symbol(signal)
        instrument = self._instruments[symbol]
        exchange = self._signal_exchange(signal) or instrument.exchange
        benchmark_symbol = instrument.benchmark
        instrument_outcome = self._symbol_outcome(
            symbol=symbol,
            exchange=exchange,
            event_at=event_at,
        )
        benchmark_outcome = (
            self._symbol_outcome(
                symbol=benchmark_symbol,
                exchange=self._benchmark_exchange(benchmark_symbol, fallback_exchange=exchange),
                event_at=event_at,
            )
            if benchmark_symbol
            else None
        )
        benchmark_returns = benchmark_outcome.returns if benchmark_outcome else {}
        abnormal_returns = self._abnormal_returns(
            instrument_outcome.returns,
            benchmark_returns,
        )
        outcome_status = self._outcome_status(instrument_outcome)
        return {
            "event_id": event.get("event_id"),
            "signal_id": signal.get("signal_id"),
            "cluster_id": event.get("cluster_id") or signal.get("cluster_id"),
            "symbol": symbol,
            "exchange": exchange,
            "benchmark_symbol": benchmark_symbol,
            "event_time": event_at.isoformat(),
            "event_type": event.get("event_type", "unknown"),
            "event_subtype": event.get("event_subtype", "unknown"),
            "event_status": event.get("event_status", "unknown"),
            "headline": event.get("headline", ""),
            "direction": self._signal_metrics(signal).get("direction"),
            "signal_score": self._signal_metrics(signal).get("signal_score"),
            "confidence": self._signal_metrics(signal).get("confidence"),
            "quality": self._signal_metrics(signal).get("quality"),
            "market_anchor_at": instrument_outcome.market_anchor_at.isoformat(),
            "anchor_source": instrument_outcome.anchor_source,
            "market_session": instrument_outcome.market_session,
            "price_at_event": instrument_outcome.price_at_event,
            "price_source": instrument_outcome.price_source,
            "returns": instrument_outcome.returns,
            "benchmark_returns": benchmark_returns,
            "abnormal_returns": abnormal_returns,
            "maximum_favourable_excursion_5d": instrument_outcome.maximum_favourable_excursion_5d,
            "maximum_adverse_excursion_5d": instrument_outcome.maximum_adverse_excursion_5d,
            "outcome_status": outcome_status,
            "confounder_grade": (
                "unreviewed" if outcome_status != "missing_market_data" else "unusable"
            ),
            "bars_available": instrument_outcome.bars_available,
            "notes": instrument_outcome.notes,
            "calibration_profile": self._profile_key(event),
        }

    def _symbol_outcome(
        self,
        *,
        symbol: str,
        exchange: str | None,
        event_at: datetime,
    ) -> _SymbolOutcome:
        search_start = event_at - timedelta(days=2)
        search_end = event_at + timedelta(days=35)
        intraday_bars, intraday_interval = self._best_intraday_bars(
            symbol=symbol,
            exchange=exchange,
            start_at=search_start,
            end_at=search_end,
        )
        daily_bars = self._market_bars(
            symbol=symbol,
            exchange=exchange,
            interval=MarketDataInterval.DAILY,
            start_at=search_start,
            end_at=search_end,
        )
        anchor = self._timer.anchor_event(
            event_at=event_at,
            exchange=self._timer_exchange(exchange),
            available_bars=intraday_bars,
        )
        notes = list(anchor.notes)
        price_at_event: float | None = None
        price_source: str | None = None
        anchor_intraday_bar = self._first_bar_at_or_after(intraday_bars, anchor.market_anchor_at)
        if anchor_intraday_bar is not None and intraday_interval is not None:
            price_at_event = anchor_intraday_bar.close
            price_source = f"{intraday_interval.value}_bar"
        baseline_daily_index = self._daily_index_at_or_after(daily_bars, anchor.market_anchor_at)
        if price_at_event is None and baseline_daily_index is not None:
            price_at_event = self._close_price(daily_bars[baseline_daily_index])
            price_source = "daily_close"
            notes.append(
                "Daily close used as event price because cached intraday bars are unavailable."
            )

        returns = self._returns(
            price_at_event=price_at_event,
            price_source=price_source,
            anchor_at=anchor.market_anchor_at,
            intraday_bars=intraday_bars,
            daily_bars=daily_bars,
            baseline_daily_index=baseline_daily_index,
        )
        mfe, mae = self._excursions_5d(
            price_at_event=price_at_event,
            daily_bars=daily_bars,
            baseline_daily_index=baseline_daily_index,
        )
        if price_at_event is None:
            notes.append("No cached market bar is available at or after the event anchor.")
        return _SymbolOutcome(
            symbol=symbol,
            exchange=exchange,
            price_at_event=price_at_event,
            price_source=price_source,
            market_anchor_at=anchor.market_anchor_at,
            anchor_source=anchor.anchor_source,
            market_session=anchor.session.value,
            returns=returns,
            maximum_favourable_excursion_5d=mfe,
            maximum_adverse_excursion_5d=mae,
            bars_available={
                "intraday": len(intraday_bars),
                "daily": len(daily_bars),
            },
            notes=notes,
        )

    def _returns(
        self,
        *,
        price_at_event: float | None,
        price_source: str | None,
        anchor_at: datetime,
        intraday_bars: list[MarketDataBar],
        daily_bars: list[MarketDataBar],
        baseline_daily_index: int | None,
    ) -> dict[str, float | None]:
        returns: dict[str, float | None] = {}
        for label, delta in INTRADAY_WINDOWS.items():
            target_bar = self._first_bar_at_or_after(intraday_bars, anchor_at + delta)
            returns[label] = self._return(price_at_event, target_bar.close if target_bar else None)

        returns["end_of_day"] = None
        if price_source != "daily_close" and baseline_daily_index is not None:
            returns["end_of_day"] = self._return(
                price_at_event,
                self._close_price(daily_bars[baseline_daily_index]),
            )

        for label, offset in DAILY_WINDOWS.items():
            target_index = (
                baseline_daily_index + offset if baseline_daily_index is not None else None
            )
            target_close = (
                self._close_price(daily_bars[target_index])
                if target_index is not None and target_index < len(daily_bars)
                else None
            )
            returns[label] = self._return(price_at_event, target_close)
        return returns

    def _excursions_5d(
        self,
        *,
        price_at_event: float | None,
        daily_bars: list[MarketDataBar],
        baseline_daily_index: int | None,
    ) -> tuple[float | None, float | None]:
        if price_at_event is None or baseline_daily_index is None:
            return None, None
        window = daily_bars[baseline_daily_index : baseline_daily_index + 6]
        if not window:
            return None, None
        favourable = max(self._return(price_at_event, bar.high) or 0.0 for bar in window)
        adverse = min(self._return(price_at_event, bar.low) or 0.0 for bar in window)
        return round(favourable, 6), round(adverse, 6)

    def _abnormal_returns(
        self,
        returns: dict[str, float | None],
        benchmark_returns: dict[str, float | None],
    ) -> dict[str, float | None]:
        abnormal: dict[str, float | None] = {}
        for key, value in returns.items():
            benchmark_value = benchmark_returns.get(key)
            abnormal[key] = (
                round(value - benchmark_value, 6)
                if value is not None and benchmark_value is not None
                else None
            )
        return abnormal

    def _profile_summaries(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            grouped.setdefault(str(row["calibration_profile"]), []).append(row)
        summaries: list[dict[str, Any]] = []
        for profile, profile_rows in sorted(grouped.items()):
            summaries.append(
                {
                    "calibration_profile": profile,
                    "sample_size": len(profile_rows),
                    "usable_outcomes": sum(
                        1 for row in profile_rows if row["outcome_status"] != "missing_market_data"
                    ),
                    "median_abnormal_return_30m": self._median_abnormal(profile_rows, "30m"),
                    "median_abnormal_return_1d": self._median_abnormal(profile_rows, "1d"),
                    "median_abnormal_return_5d": self._median_abnormal(profile_rows, "5d"),
                }
            )
        return summaries

    def _median_abnormal(self, rows: list[dict[str, Any]], key: str) -> float | None:
        values = [
            float(row["abnormal_returns"][key])
            for row in rows
            if isinstance(row.get("abnormal_returns"), dict)
            and row["abnormal_returns"].get(key) is not None
        ]
        return round(float(median(values)), 6) if values else None

    def _best_intraday_bars(
        self,
        *,
        symbol: str,
        exchange: str | None,
        start_at: datetime,
        end_at: datetime,
    ) -> tuple[list[MarketDataBar], MarketDataInterval | None]:
        for interval in INTRADAY_INTERVALS:
            bars = self._market_bars(
                symbol=symbol,
                exchange=exchange,
                interval=interval,
                start_at=start_at,
                end_at=end_at,
            )
            if bars:
                return bars, interval
        return [], None

    def _market_bars(
        self,
        *,
        symbol: str,
        exchange: str | None,
        interval: MarketDataInterval,
        start_at: datetime,
        end_at: datetime,
    ) -> list[MarketDataBar]:
        bars = self._repositories.market_bars.list_range(
            symbol=symbol,
            exchange=exchange,
            interval=interval,
            start_at=start_at,
            end_at=end_at,
        )
        if not bars and exchange:
            bars = self._repositories.market_bars.list_range(
                symbol=symbol,
                exchange=None,
                interval=interval,
                start_at=start_at,
                end_at=end_at,
            )
        return bars

    def _daily_index_at_or_after(
        self,
        daily_bars: list[MarketDataBar],
        target_at: datetime,
    ) -> int | None:
        target_day = datetime.combine(to_utc(target_at).date(), time.min, tzinfo=UTC)
        for index, bar in enumerate(daily_bars):
            if bar.timestamp_utc >= target_day:
                return index
        return None

    def _first_bar_at_or_after(
        self,
        bars: list[MarketDataBar],
        target_at: datetime,
    ) -> MarketDataBar | None:
        for bar in sorted(bars, key=lambda item: item.timestamp_utc):
            if bar.timestamp_utc >= target_at:
                return bar
        return None

    def _return(self, start_price: float | None, end_price: float | None) -> float | None:
        if start_price is None or end_price is None or start_price == 0:
            return None
        return round((end_price - start_price) / start_price, 6)

    def _close_price(self, bar: MarketDataBar) -> float:
        return bar.adjusted_close if bar.adjusted_close is not None else bar.close

    def _outcome_status(self, outcome: _SymbolOutcome) -> str:
        if outcome.price_at_event is None:
            return "missing_market_data"
        if all(value is None for value in outcome.returns.values()):
            return "price_only"
        if any(value is None for value in outcome.returns.values()):
            return "partial"
        return "complete"

    def _signal_symbol(self, signal: dict[str, Any]) -> str:
        instrument = signal.get("instrument", {})
        if not isinstance(instrument, dict):
            return ""
        return str(instrument.get("symbol", "")).upper()

    def _signal_exchange(self, signal: dict[str, Any]) -> str | None:
        instrument = signal.get("instrument", {})
        if not isinstance(instrument, dict):
            return None
        exchange = instrument.get("exchange")
        return str(exchange).upper() if exchange else None

    def _signal_metrics(self, signal: dict[str, Any]) -> dict[str, Any]:
        metrics = signal.get("signal", {})
        return metrics if isinstance(metrics, dict) else {}

    def _event_time(
        self,
        event: dict[str, Any],
        signal: dict[str, Any],
    ) -> datetime | None:
        timestamps = event.get("timestamps", {})
        if isinstance(timestamps, dict):
            for key in ("published_at", "event_effective_at", "processed_at"):
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

    def _profile_key(self, event: dict[str, Any]) -> str:
        return "_".join(
            str(part)
            for part in [
                event.get("event_type", "unknown"),
                event.get("event_subtype", "unknown"),
                event.get("event_scope", "unknown"),
            ]
        )

    def _benchmark_exchange(self, symbol: str, *, fallback_exchange: str | None) -> str | None:
        instrument = self._instruments.get(symbol.upper())
        if instrument is not None:
            return instrument.exchange
        return fallback_exchange

    def _timer_exchange(self, exchange: str | None) -> str:
        if not exchange:
            return "US"
        upper = exchange.upper()
        if upper in {"NASDAQ", "NYSE", "LSE", "US"}:
            return upper
        if "LSE" in upper or "LONDON" in upper:
            return "LSE"
        return "US"
