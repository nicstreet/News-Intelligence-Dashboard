from __future__ import annotations

import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any, cast

from news_intelligence.config import NewsIntelligenceConfig
from news_intelligence.http_client import transport_error_detail, urlopen
from news_intelligence.models import NewsSource, RawNewsItem, RuntimeEnvironment, SourceIngestedItem
from news_intelligence.utils import normalise_whitespace, stable_hash, to_utc

TextFetcher = Callable[[str, dict[str, str], int], str]


class OfficialFeedConnector:
    def __init__(
        self,
        config: NewsIntelligenceConfig,
        source_config: dict[str, Any],
        *,
        fetcher: TextFetcher | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._config = config
        self._settings = source_config
        self.adapter_id = str(
            source_config.get("source_id", source_config.get("source_name", "official_feed"))
        )
        self.source_name = str(source_config.get("source_name", self.adapter_id))
        self.connector_type = str(source_config.get("connector_type", "official_feed"))
        self.enabled = bool(source_config.get("enabled", False))
        self.poll_interval = timedelta(
            seconds=int(source_config.get("poll_interval_seconds", 1800))
        )
        self.country_or_region = str(source_config.get("country_or_region", "unknown"))
        self.source_class = str(source_config.get("source_class", "official"))
        self.source_type = str(source_config.get("source_type", self.source_class))
        self.url = str(source_config.get("url", ""))
        self.timeout_seconds = int(source_config.get("timeout_seconds", 20))
        self.max_retries = int(source_config.get("max_retries", 2))
        self.use_environment_proxy = bool(source_config.get("use_environment_proxy", False))
        self.limit = max(1, int(source_config.get("limit", 25)))
        self._fetcher = fetcher or self._fetch_text
        self._clock = clock or (lambda: datetime.now(UTC))

    def fetch(
        self,
        known_source_record_ids: set[str] | None = None,
    ) -> Sequence[SourceIngestedItem]:
        if not self.enabled or not self.url:
            return []
        known = known_source_record_ids or set()
        text = self._fetcher(self.url, self._headers(), self.timeout_seconds)
        records = self._parse_feed(text)
        return [record for record in records if record.source_record_id not in known][: self.limit]

    def to_raw_news_item(self, item: SourceIngestedItem) -> RawNewsItem:
        metadata = dict(item.metadata)
        return RawNewsItem(
            raw_id=stable_hash(self.connector_type, item.source_record_id, prefix="raw_"),
            headline=item.headline,
            body=str(metadata.pop("body", "")),
            source=NewsSource(
                source_name=item.source_name,
                source_type=self.source_type,
                source_url=item.source_url,
            ),
            published_at=item.published_at,
            first_seen_at=item.ingested_at,
            source_article_id=item.source_record_id,
            country=self.country_or_region,
            record_environment=self._runtime_environment(),
            metadata={**metadata, "connector_type": self.connector_type},
        )

    def _parse_feed(self, text: str) -> list[SourceIngestedItem]:
        root = ET.fromstring(text)
        entries = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
        records: list[SourceIngestedItem] = []
        for entry in entries:
            title = normalise_whitespace(self._child_text(entry, "title") or "Official feed item")
            url = self._link(entry)
            published_at = self._published_at(entry)
            body = normalise_whitespace(
                self._child_text(entry, "description")
                or self._child_text(entry, "summary")
                or self._child_text(entry, "content")
                or ""
            )
            source_record_id = self._record_id(
                entry,
                title=title,
                url=url,
                published_at=published_at,
            )
            records.append(
                SourceIngestedItem(
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
                        "authority_level": self._settings.get("authority_level", "official"),
                        "region": self.country_or_region,
                    },
                )
            )
        records.sort(key=lambda record: record.published_at, reverse=True)
        return records

    def _child_text(self, entry: ET.Element, local_name: str) -> str:
        for child in entry.iter():
            if self._local_name(child.tag) == local_name:
                return child.text or ""
        return ""

    def _link(self, entry: ET.Element) -> str | None:
        for child in entry.iter():
            if self._local_name(child.tag) != "link":
                continue
            href = child.attrib.get("href")
            if href:
                return href
            if child.text:
                return child.text.strip()
        return None

    def _published_at(self, entry: ET.Element) -> datetime:
        for key in ("pubDate", "published", "updated", "date"):
            value = self._child_text(entry, key)
            if not value:
                continue
            try:
                if "," in value:
                    return to_utc(parsedate_to_datetime(value))
                return to_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
            except (TypeError, ValueError):
                continue
        return self._clock()

    def _record_id(
        self,
        entry: ET.Element,
        *,
        title: str,
        url: str | None,
        published_at: datetime,
    ) -> str:
        guid = self._child_text(entry, "guid") or self._child_text(entry, "id")
        if guid:
            return f"{self.connector_type}:{stable_hash(guid, length=24)}"
        return stable_hash(
            self.connector_type,
            title,
            url,
            published_at.isoformat(),
            prefix=f"{self.connector_type}:",
            length=24,
        )

    def _fetch_text(self, url: str, headers: dict[str, str], timeout: int) -> str:
        for attempt in range(self.max_retries + 1):
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
                        f"Official feed request failed: {transport_error_detail(exc)}"
                    ) from exc
                time.sleep(2**attempt)
            except urllib.error.URLError as exc:
                if attempt >= self.max_retries:
                    raise RuntimeError(
                        f"Official feed request failed: {transport_error_detail(exc)}"
                    ) from exc
                time.sleep(2**attempt)
        raise RuntimeError("Official feed request failed after retries")

    def _headers(self) -> dict[str, str]:
        return {"User-Agent": "Asterius News Intelligence official feed monitor"}

    def _local_name(self, value: str) -> str:
        return value.rsplit("}", 1)[-1]

    def _runtime_environment(self) -> RuntimeEnvironment:
        try:
            return RuntimeEnvironment(self._config.environment)
        except ValueError:
            return RuntimeEnvironment.DEVELOPMENT


def configured_official_feed_connectors(
    config: NewsIntelligenceConfig,
    *,
    fetcher: TextFetcher | None = None,
    clock: Callable[[], datetime] | None = None,
) -> list[OfficialFeedConnector]:
    sources = config.official_sources.get("sources", [])
    if not isinstance(sources, list):
        return []
    return [
        OfficialFeedConnector(config, source, fetcher=fetcher, clock=clock)
        for source in sources
        if isinstance(source, dict)
    ]
