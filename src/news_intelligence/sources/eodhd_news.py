from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any, cast

from news_intelligence.config import NewsIntelligenceConfig
from news_intelligence.models import NewsSource, RawNewsItem, RuntimeEnvironment, SourceIngestedItem
from news_intelligence.utils import normalise_whitespace, stable_hash, to_utc

TextFetcher = Callable[[str, dict[str, str], int], str]


class EodhdNewsConnector:
    adapter_id = "eodhd_news"
    country_or_region = "global"
    source_class = "financial_news"

    def __init__(
        self,
        config: NewsIntelligenceConfig,
        *,
        fetcher: TextFetcher | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._config = config
        self._settings = self._news_settings()
        self.source_name = str(self._settings.get("source_name", "EODHD Financial News"))
        self.connector_type = str(self._settings.get("connector_type", "eodhd_news"))
        self.enabled = bool(self._settings.get("enabled", False))
        self.poll_interval = timedelta(
            seconds=int(self._settings.get("poll_interval_seconds", 900))
        )
        self.timeout_seconds = int(
            self._settings.get("timeout_seconds", config.eodhd.get("timeout_seconds", 20))
        )
        self.max_retries = int(
            self._settings.get("max_retries", config.eodhd.get("max_retries", 3))
        )
        self.base_url = str(config.eodhd.get("base_url", "https://eodhd.com/api")).rstrip("/")
        self.endpoint = str(self._settings.get("endpoint", "/news"))
        self.limit = max(1, int(self._settings.get("limit", 50)))
        self.lookback_hours = max(1, int(self._settings.get("lookback_hours", 48)))
        self.rate_limit_per_minute = max(
            1,
            int(
                self._settings.get(
                    "rate_limit_per_minute",
                    config.eodhd.get("rate_limit_per_minute", 60),
                )
            ),
        )
        self._fetcher = fetcher or self._fetch_text
        self._clock = clock or (lambda: datetime.now(UTC))
        self._last_request_at = 0.0

    def fetch(
        self,
        known_source_record_ids: set[str] | None = None,
    ) -> Sequence[SourceIngestedItem]:
        if not self.enabled or not self._config.eodhd_api_token:
            return []
        known = known_source_record_ids or set()
        payload = self._get_json(
            self._parameters(
                start=(self._clock() - timedelta(hours=self.lookback_hours)).date(),
                end=self._clock().date(),
                limit=self.limit,
                offset=0,
            )
        )
        if not isinstance(payload, list):
            return []
        records: list[SourceIngestedItem] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            record = self._record_from_payload(item)
            if record.source_record_id not in known:
                records.append(record)
        records.sort(key=lambda item: item.published_at, reverse=True)
        return records

    def fetch_range(
        self,
        *,
        start: date,
        end: date,
        known_source_record_ids: set[str] | None = None,
        limit: int | None = None,
        max_pages: int | None = None,
        symbols: list[str] | None = None,
    ) -> Sequence[SourceIngestedItem]:
        if not self.enabled or not self._config.eodhd_api_token:
            return []
        if end < start:
            raise ValueError("Backfill end date must be on or after the start date.")

        known = known_source_record_ids or set()
        page_limit = max(1, int(limit or self.limit))
        page_count = max(
            1,
            int(max_pages or self._settings.get("backfill_max_pages", 100)),
        )
        records: list[SourceIngestedItem] = []
        seen: set[str] = set()
        for page in range(page_count):
            offset = page * page_limit
            payload = self._get_json(
                self._parameters(
                    start=start,
                    end=end,
                    limit=page_limit,
                    offset=offset,
                    symbols=symbols,
                )
            )
            if not isinstance(payload, list) or not payload:
                break
            for item in payload:
                if not isinstance(item, dict):
                    continue
                record = self._record_from_payload(item)
                if record.source_record_id in known or record.source_record_id in seen:
                    continue
                records.append(record)
                seen.add(record.source_record_id)
            if len(payload) < page_limit:
                break
        records.sort(key=lambda item: item.published_at)
        return records

    def to_raw_news_item(self, item: SourceIngestedItem) -> RawNewsItem:
        metadata = dict(item.metadata)
        tickers = metadata.pop("tickers", [])
        body = str(metadata.pop("body", ""))
        return RawNewsItem(
            raw_id=stable_hash(self.connector_type, item.source_record_id, prefix="raw_"),
            headline=item.headline,
            body=body,
            source=NewsSource(
                source_name=item.source_name,
                source_type=str(self._settings.get("source_type", "newswire")),
                source_url=item.source_url,
            ),
            published_at=item.published_at,
            first_seen_at=item.ingested_at,
            source_article_id=item.source_record_id,
            tickers=[str(ticker).upper() for ticker in tickers if ticker],
            known_ticker=str(tickers[0]).upper() if tickers else None,
            record_environment=self._runtime_environment(),
            metadata={**metadata, "connector_type": self.connector_type},
        )

    def _parameters(
        self,
        *,
        start: date,
        end: date,
        limit: int,
        offset: int,
        symbols: list[str] | None = None,
    ) -> dict[str, str]:
        selected_symbols = symbols or self._symbols()
        parameters = {
            "api_token": self._config.eodhd_api_token,
            "fmt": "json",
            "limit": str(limit),
            "offset": str(offset),
            "from": start.isoformat(),
            "to": end.isoformat(),
        }
        if selected_symbols:
            parameters["s"] = ",".join(selected_symbols)
        return parameters

    def _symbols(self) -> list[str]:
        configured = self._settings.get("symbols", [])
        if isinstance(configured, list) and configured:
            return [str(symbol).upper() for symbol in configured if symbol]
        favourites = self._config.favourite_instruments()
        max_symbols = max(1, int(self._settings.get("max_symbols", 200)))
        return [
            str(instrument.get("symbol", "")).upper()
            for instrument in favourites[:max_symbols]
            if instrument.get("symbol")
        ]

    def _record_from_payload(self, item: dict[str, Any]) -> SourceIngestedItem:
        published_at = self._published_at(item)
        url = str(item.get("link") or item.get("url") or "").strip() or None
        title = normalise_whitespace(
            str(item.get("title") or item.get("headline") or "EODHD news item")
        )
        body = normalise_whitespace(
            str(item.get("content") or item.get("text") or item.get("summary") or "")
        )
        tickers = self._tickers(item)
        source_record_id = str(item.get("id") or "").strip()
        if not source_record_id:
            source_record_id = stable_hash(
                self.connector_type,
                title,
                published_at.isoformat(),
                url,
                prefix=f"{self.connector_type}:",
                length=24,
            )
        return SourceIngestedItem(
            source_record_id=source_record_id,
            source_name=self.source_name,
            connector_type=self.connector_type,
            headline=title,
            published_at=published_at,
            source_url=url,
            ingested_at=self._clock(),
            record_environment=self._runtime_environment(),
            metadata={
                "body": body,
                "tickers": tickers,
                "symbols": tickers,
                "source_payload": {
                    key: value
                    for key, value in item.items()
                    if key not in {"content", "text"}
                },
            },
        )

    def _tickers(self, item: dict[str, Any]) -> list[str]:
        candidates = item.get("symbols") or item.get("tickers") or item.get("tags") or []
        if isinstance(candidates, str):
            candidates = [candidates]
        if not isinstance(candidates, list):
            return []
        symbols: list[str] = []
        for value in candidates:
            symbol = str(value).split(".")[0].upper().strip()
            if symbol and symbol not in symbols:
                symbols.append(symbol)
        return symbols

    def _published_at(self, item: dict[str, Any]) -> datetime:
        for key in ("date", "published_at", "publishedDate", "created_at"):
            value = item.get(key)
            if not value:
                continue
            try:
                candidate = str(value).replace("Z", "+00:00")
                return to_utc(datetime.fromisoformat(candidate))
            except ValueError:
                continue
        return self._clock()

    def _get_json(self, parameters: dict[str, str]) -> Any:
        query = urllib.parse.urlencode(parameters)
        text = self._fetcher(
            f"{self.base_url}{self.endpoint}?{query}",
            self._headers(),
            self.timeout_seconds,
        )
        return json.loads(text)

    def _fetch_text(self, url: str, headers: dict[str, str], timeout: int) -> str:
        for attempt in range(self.max_retries + 1):
            self._respect_rate_limit()
            request = urllib.request.Request(url, headers=headers)
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    return cast(bytes, response.read()).decode("utf-8", errors="replace")
            except urllib.error.HTTPError as exc:
                if exc.code not in {429, 500, 502, 503, 504} or attempt >= self.max_retries:
                    raise RuntimeError("EODHD news request failed") from exc
                time.sleep(2**attempt)
            except urllib.error.URLError as exc:
                if attempt >= self.max_retries:
                    raise RuntimeError("EODHD news request failed") from exc
                time.sleep(2**attempt)
        raise RuntimeError("EODHD news request failed after retries")

    def _respect_rate_limit(self) -> None:
        minimum_interval = 60.0 / self.rate_limit_per_minute
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < minimum_interval:
            time.sleep(minimum_interval - elapsed)
        self._last_request_at = time.monotonic()

    def _headers(self) -> dict[str, str]:
        return {"User-Agent": "Asterius News Intelligence EODHD news"}

    def _news_settings(self) -> dict[str, Any]:
        settings = self._config.eodhd.get("news", {})
        return settings if isinstance(settings, dict) else {}

    def _runtime_environment(self) -> RuntimeEnvironment:
        try:
            return RuntimeEnvironment(self._config.environment)
        except ValueError:
            return RuntimeEnvironment.DEVELOPMENT
