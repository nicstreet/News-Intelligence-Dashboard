from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any, cast

from news_intelligence.config import NewsIntelligenceConfig
from news_intelligence.http_client import redact_url, transport_error_detail, urlopen
from news_intelligence.models import MarketDataBar, MarketDataInterval, RuntimeEnvironment
from news_intelligence.utils import to_utc

TextFetcher = Callable[[str, dict[str, str], int], str]


class EodhdMarketDataClient:
    def __init__(
        self,
        config: NewsIntelligenceConfig,
        *,
        fetcher: TextFetcher | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._config = config
        self._settings = config.eodhd
        self.source_name = str(self._settings.get("source_name", "EODHD"))
        self.enabled = bool(self._settings.get("enabled", False))
        self.base_url = str(self._settings.get("base_url", "https://eodhd.com/api")).rstrip("/")
        self.timeout_seconds = int(self._settings.get("timeout_seconds", 20))
        self.max_retries = int(self._settings.get("max_retries", 3))
        self.use_environment_proxy = bool(self._settings.get("use_environment_proxy", False))
        self.rate_limit_per_minute = max(
            1,
            int(self._settings.get("rate_limit_per_minute", 60)),
        )
        self._fetcher = fetcher or self._fetch_text
        self._clock = clock or (lambda: datetime.now(UTC))
        self._last_request_at = 0.0

    def fetch_daily_bars(
        self,
        *,
        symbol: str,
        exchange: str | None,
        start: date,
        end: date,
    ) -> list[MarketDataBar]:
        eodhd_symbol = self.eodhd_symbol(symbol, exchange)
        payload = self._get_json(
            f"/eod/{urllib.parse.quote(eodhd_symbol)}",
            {
                "from": start.isoformat(),
                "to": end.isoformat(),
                "period": str(self._settings.get("historical_eod", {}).get("default_period", "d")),
                "order": "a",
                "fmt": "json",
            },
        )
        if not isinstance(payload, list):
            return []
        return [
            self._daily_bar(item, symbol=symbol, exchange=exchange)
            for item in payload
            if isinstance(item, dict)
        ]

    def fetch_intraday_bars(
        self,
        *,
        symbol: str,
        exchange: str | None,
        interval: MarketDataInterval,
        start_at: datetime,
        end_at: datetime,
    ) -> list[MarketDataBar]:
        if interval == MarketDataInterval.DAILY:
            raise ValueError("Use fetch_daily_bars for daily market data")
        eodhd_symbol = self.eodhd_symbol(symbol, exchange)
        payload = self._get_json(
            f"/intraday/{urllib.parse.quote(eodhd_symbol)}",
            {
                "interval": interval.value,
                "from": str(int(to_utc(start_at).timestamp())),
                "to": str(int(to_utc(end_at).timestamp())),
                "fmt": "json",
            },
        )
        if not isinstance(payload, list):
            return []
        return [
            self._intraday_bar(item, symbol=symbol, exchange=exchange, interval=interval)
            for item in payload
            if isinstance(item, dict)
        ]

    def eodhd_symbol(self, symbol: str, exchange: str | None = None) -> str:
        clean_symbol = symbol.upper().strip()
        clean_exchange = exchange.upper().strip() if exchange else ""
        suffixes = self._settings.get("exchange_suffixes", {})
        suffix_map = suffixes if isinstance(suffixes, dict) else {}

        if "." in clean_symbol:
            base, supplied_suffix = clean_symbol.rsplit(".", 1)
            if supplied_suffix == "L":
                mapped = str(suffix_map.get("LSE", "LSE"))
                return f"{base}.{mapped}"
            return clean_symbol

        mapped_suffix = suffix_map.get(clean_exchange) or suffix_map.get("US")
        return f"{clean_symbol}.{mapped_suffix}" if mapped_suffix else clean_symbol

    def estimated_call_cost(self, interval: MarketDataInterval) -> int:
        if interval == MarketDataInterval.DAILY:
            return 1
        return 5

    def _get_json(self, endpoint: str, parameters: dict[str, str]) -> Any:
        token = self._config.eodhd_api_token
        if not token:
            raise ValueError(
                "EODHD API token is missing; set EODHD_API_TOKEN or config/eodhd.local.yaml"
            )
        query = urllib.parse.urlencode({**parameters, "api_token": token})
        url = f"{self.base_url}{endpoint}?{query}"
        text = self._fetcher(url, self._headers(), self.timeout_seconds)
        payload = json.loads(text)
        if isinstance(payload, dict) and payload.get("error"):
            raise RuntimeError(f"EODHD returned an error for {endpoint}")
        if isinstance(payload, dict) and payload.get("message") and not payload.get("date"):
            raise RuntimeError(f"EODHD returned a message for {endpoint}")
        return payload

    def _fetch_text(self, url: str, headers: dict[str, str], timeout: int) -> str:
        for attempt in range(self.max_retries + 1):
            self._respect_rate_limit()
            request = urllib.request.Request(url, headers=headers)
            try:
                with urlopen(
                    request,
                    timeout=timeout,
                    use_environment_proxy=self.use_environment_proxy,
                ) as response:
                    return cast(bytes, response.read()).decode("utf-8", errors="replace")
            except urllib.error.HTTPError as exc:
                if exc.code not in {429, 500, 502, 503, 504} or attempt >= self.max_retries:
                    raise RuntimeError(
                        "EODHD request failed: "
                        f"{transport_error_detail(exc)} ({redact_url(url)})"
                    ) from exc
                retry_after = exc.headers.get("Retry-After")
                delay = float(retry_after) if retry_after and retry_after.isdigit() else 2**attempt
                time.sleep(delay)
            except urllib.error.URLError as exc:
                if attempt >= self.max_retries:
                    raise RuntimeError(
                        "EODHD request failed: "
                        f"{transport_error_detail(exc)} ({redact_url(url)})"
                    ) from exc
                time.sleep(2**attempt)
        raise RuntimeError("EODHD request failed after retries")

    def _respect_rate_limit(self) -> None:
        minimum_interval = 60.0 / self.rate_limit_per_minute
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < minimum_interval:
            time.sleep(minimum_interval - elapsed)
        self._last_request_at = time.monotonic()

    def _headers(self) -> dict[str, str]:
        return {"User-Agent": "Asterius News Intelligence market data"}

    def _daily_bar(
        self,
        item: dict[str, Any],
        *,
        symbol: str,
        exchange: str | None,
    ) -> MarketDataBar:
        timestamp = datetime.fromisoformat(str(item["date"])).replace(tzinfo=UTC)
        return MarketDataBar(
            symbol=symbol,
            exchange=exchange,
            interval=MarketDataInterval.DAILY,
            timestamp_utc=timestamp,
            open=float(item["open"]),
            high=float(item["high"]),
            low=float(item["low"]),
            close=float(item["close"]),
            adjusted_close=self._optional_float(item.get("adjusted_close")),
            volume=self._optional_float(item.get("volume")),
            source_name=self.source_name,
            loaded_at=self._clock(),
            record_environment=self._record_environment(),
        )

    def _intraday_bar(
        self,
        item: dict[str, Any],
        *,
        symbol: str,
        exchange: str | None,
        interval: MarketDataInterval,
    ) -> MarketDataBar:
        timestamp = self._intraday_timestamp(item)
        return MarketDataBar(
            symbol=symbol,
            exchange=exchange,
            interval=interval,
            timestamp_utc=timestamp,
            open=float(item["open"]),
            high=float(item["high"]),
            low=float(item["low"]),
            close=float(item["close"]),
            adjusted_close=None,
            volume=self._optional_float(item.get("volume")),
            source_name=self.source_name,
            loaded_at=self._clock(),
            record_environment=self._record_environment(),
        )

    def _intraday_timestamp(self, item: dict[str, Any]) -> datetime:
        if item.get("timestamp") is not None:
            return datetime.fromtimestamp(int(item["timestamp"]), tz=UTC)
        raw = str(item.get("datetime") or item.get("date"))
        if raw.endswith("Z"):
            raw = f"{raw[:-1]}+00:00"
        parsed = datetime.fromisoformat(raw)
        return to_utc(parsed)

    def _optional_float(self, value: Any) -> float | None:
        return float(value) if value is not None and value != "" else None

    def _record_environment(self) -> RuntimeEnvironment:
        try:
            return RuntimeEnvironment(self._config.environment)
        except ValueError:
            return RuntimeEnvironment.DEVELOPMENT
