from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from news_intelligence.models import MarketDataBar, MarketEventAnchor, MarketSession
from news_intelligence.utils import to_utc


@dataclass(frozen=True)
class ExchangeHours:
    exchange: str
    timezone: str
    regular_open: time
    regular_close: time
    pre_market_open: time | None = None
    after_hours_close: time | None = None


EXCHANGE_HOURS = {
    "NASDAQ": ExchangeHours(
        exchange="NASDAQ",
        timezone="America/New_York",
        regular_open=time(9, 30),
        regular_close=time(16, 0),
        pre_market_open=time(4, 0),
        after_hours_close=time(20, 0),
    ),
    "NYSE": ExchangeHours(
        exchange="NYSE",
        timezone="America/New_York",
        regular_open=time(9, 30),
        regular_close=time(16, 0),
        pre_market_open=time(4, 0),
        after_hours_close=time(20, 0),
    ),
    "US": ExchangeHours(
        exchange="US",
        timezone="America/New_York",
        regular_open=time(9, 30),
        regular_close=time(16, 0),
        pre_market_open=time(4, 0),
        after_hours_close=time(20, 0),
    ),
    "LSE": ExchangeHours(
        exchange="LSE",
        timezone="Europe/London",
        regular_open=time(8, 0),
        regular_close=time(16, 30),
    ),
}


class EventMarketTimer:
    def anchor_event(
        self,
        *,
        event_at: datetime,
        exchange: str,
        available_bars: list[MarketDataBar] | None = None,
        holidays: set[str] | None = None,
    ) -> MarketEventAnchor:
        hours = self._hours(exchange)
        event_utc = to_utc(event_at)
        matching_bar = self._first_bar_at_or_after(event_utc, available_bars or [])
        session = self.classify_session(
            event_at=event_utc,
            exchange=hours.exchange,
            holidays=holidays,
        )
        calendar_anchor = self.next_regular_session_open(
            event_at=event_utc,
            exchange=hours.exchange,
            holidays=holidays,
        )
        if session == MarketSession.REGULAR_SESSION:
            calendar_anchor = event_utc
        if matching_bar is not None:
            notes = ["Anchored to first cached market-data bar at or after event timestamp."]
            return MarketEventAnchor(
                event_timestamp=event_utc,
                exchange=hours.exchange,
                session=session,
                market_anchor_at=matching_bar.timestamp_utc,
                anchor_source="available_bar",
                regular_session_anchor_at=calendar_anchor,
                notes=notes,
            )
        return MarketEventAnchor(
            event_timestamp=event_utc,
            exchange=hours.exchange,
            session=session,
            market_anchor_at=calendar_anchor,
            anchor_source="session_calendar",
            regular_session_anchor_at=calendar_anchor,
            notes=[
                "No cached intraday bar was supplied; anchored using configured exchange hours.",
            ],
        )

    def classify_session(
        self,
        *,
        event_at: datetime,
        exchange: str,
        holidays: set[str] | None = None,
    ) -> MarketSession:
        hours = self._hours(exchange)
        local = to_utc(event_at).astimezone(ZoneInfo(hours.timezone))
        if local.weekday() >= 5:
            return MarketSession.WEEKEND
        if holidays and local.date().isoformat() in holidays:
            return MarketSession.HOLIDAY
        local_time = local.time()
        if hours.pre_market_open and hours.pre_market_open <= local_time < hours.regular_open:
            return MarketSession.PRE_MARKET
        if hours.regular_open <= local_time < hours.regular_close:
            return MarketSession.REGULAR_SESSION
        if hours.after_hours_close and hours.regular_close <= local_time < hours.after_hours_close:
            return MarketSession.AFTER_HOURS
        return MarketSession.CLOSED

    def next_regular_session_open(
        self,
        *,
        event_at: datetime,
        exchange: str,
        holidays: set[str] | None = None,
    ) -> datetime:
        hours = self._hours(exchange)
        local = to_utc(event_at).astimezone(ZoneInfo(hours.timezone))
        candidate_date = local.date()
        candidate_open = datetime.combine(
            candidate_date,
            hours.regular_open,
            tzinfo=ZoneInfo(hours.timezone),
        )
        if local.weekday() < 5 and local < candidate_open and not self._holiday(
            candidate_open,
            holidays,
        ):
            return candidate_open.astimezone(UTC)
        while True:
            candidate_date += timedelta(days=1)
            candidate_open = datetime.combine(
                candidate_date,
                hours.regular_open,
                tzinfo=ZoneInfo(hours.timezone),
            )
            if candidate_open.weekday() < 5 and not self._holiday(candidate_open, holidays):
                return candidate_open.astimezone(UTC)

    def _first_bar_at_or_after(
        self,
        event_utc: datetime,
        bars: list[MarketDataBar],
    ) -> MarketDataBar | None:
        candidates = sorted(
            (bar for bar in bars if bar.timestamp_utc >= event_utc),
            key=lambda bar: bar.timestamp_utc,
        )
        return candidates[0] if candidates else None

    def _hours(self, exchange: str) -> ExchangeHours:
        return EXCHANGE_HOURS.get(exchange.upper(), EXCHANGE_HOURS["US"])

    def _holiday(self, value: datetime, holidays: set[str] | None) -> bool:
        return bool(holidays and value.date().isoformat() in holidays)
