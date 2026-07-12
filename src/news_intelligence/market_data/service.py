from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any

from news_intelligence.config import NewsIntelligenceConfig
from news_intelligence.market_data.eodhd import EodhdMarketDataClient
from news_intelligence.models import MarketDataInterval, MarketDataRequest, RuntimeEnvironment
from news_intelligence.storage import RepositoryBundle
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

    def _fetch_payload(self, request: MarketDataRequest) -> dict[str, Any]:
        return {
            **request.model_dump(mode="json"),
            "token_redacted": True,
        }

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
