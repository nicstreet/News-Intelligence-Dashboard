from __future__ import annotations

import gzip
import json
import re
import time
import urllib.error
import urllib.request
import zlib
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser
from typing import Any, cast

from news_intelligence.config import NewsIntelligenceConfig
from news_intelligence.models import (
    NewsSource,
    RawNewsItem,
    RuntimeEnvironment,
    SourceIngestedFiling,
    SourceIngestedItem,
)
from news_intelligence.utils import normalise_whitespace, stable_hash, to_utc

TextFetcher = Callable[[str, dict[str, str], int], str]


class SecEdgarConnector:
    adapter_id = "sec_edgar"
    country_or_region = "US"
    source_class = "regulatory"

    def __init__(
        self,
        config: NewsIntelligenceConfig,
        *,
        fetcher: TextFetcher | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._config = config
        self._settings = config.sec_edgar
        self.source_name = str(self._settings.get("source_name", "SEC EDGAR"))
        self.connector_type = str(self._settings.get("connector_type", "sec_edgar"))
        self.enabled = bool(self._settings.get("enabled", False))
        self.forms = {str(form).upper() for form in self._settings.get("forms", ["8-K"])}
        self.poll_interval = timedelta(
            seconds=int(self._settings.get("poll_interval_seconds", 300))
        )
        self.timeout_seconds = int(self._settings.get("timeout_seconds", 15))
        self.max_retries = int(self._settings.get("max_retries", 3))
        self.max_filings_per_company = int(self._settings.get("max_filings_per_company", 5))
        self.max_requests_per_second = max(
            1.0,
            float(self._settings.get("max_requests_per_second", 5)),
        )
        self.user_agent = config.sec_edgar_user_agent
        self.base_url = str(self._settings.get("base_url", "https://data.sec.gov")).rstrip("/")
        self.archives_base_url = str(
            self._settings.get("archives_base_url", "https://www.sec.gov/Archives/edgar/data")
        ).rstrip("/")
        self._fetcher = fetcher or self._fetch_text
        self._clock = clock or (lambda: datetime.now(UTC))
        self._last_request_at = 0.0

    def fetch(
        self,
        known_source_record_ids: set[str] | None = None,
    ) -> list[SourceIngestedFiling]:
        if not self.enabled:
            return []
        known = known_source_record_ids or set()
        filings: list[SourceIngestedFiling] = []
        for company in self._companies():
            submissions = self._get_json(self._submissions_url(company["cik"]))
            filings.extend(self._filings_from_submission(company, submissions, known))
        filings.sort(key=lambda filing: filing.filing_time, reverse=True)
        return filings

    def to_raw_news_item(self, filing: SourceIngestedItem) -> RawNewsItem:
        filing = SourceIngestedFiling.model_validate(filing)
        raw_id = stable_hash(
            self.connector_type,
            filing.accession_number,
            filing.ticker,
            prefix="raw_",
        )
        return RawNewsItem(
            raw_id=raw_id,
            headline=filing.headline,
            body=self._body_from_filing(filing),
            source=NewsSource(
                source_name=self.source_name,
                source_type=str(self._settings.get("source_type", "regulatory")),
                source_url=filing.filing_url,
            ),
            published_at=filing.filing_time,
            source_article_id=filing.accession_number,
            tickers=[filing.ticker],
            known_ticker=filing.ticker,
            country="US",
            market="US",
            record_environment=RuntimeEnvironment.DEVELOPMENT,
            metadata={
                "source_connector": self.connector_type,
                "cik": filing.cik,
                "accession_number": filing.accession_number,
                "company": filing.company,
                "form_type": filing.form_type,
                "filing_url": filing.filing_url,
                "primary_document_url": filing.primary_document_url,
                "filing_sections": filing.filing_sections,
            },
        )

    def _companies(self) -> list[dict[str, str]]:
        companies = self._settings.get("companies", [])
        result: list[dict[str, str]] = []
        if not isinstance(companies, list):
            return result
        for company in companies:
            if not isinstance(company, dict):
                continue
            symbol = str(company.get("symbol", "")).upper()
            cik = self._normalise_cik(str(company.get("cik", "")))
            name = str(company.get("company", symbol))
            if symbol and cik:
                result.append({"symbol": symbol, "cik": cik, "company": name})
        return result

    def _filings_from_submission(
        self,
        company: dict[str, str],
        submissions: dict[str, Any],
        known_source_record_ids: set[str],
    ) -> list[SourceIngestedFiling]:
        recent = submissions.get("filings", {}).get("recent", {})
        if not isinstance(recent, dict):
            return []
        accession_numbers = self._column(recent, "accessionNumber")
        forms = self._column(recent, "form")
        accepted = self._column(recent, "acceptanceDateTime")
        filing_dates = self._column(recent, "filingDate")
        primary_documents = self._column(recent, "primaryDocument")
        items = self._column(recent, "items")

        filings: list[SourceIngestedFiling] = []
        considered_filings = 0
        for index, accession_number in enumerate(accession_numbers):
            form_type = self._value_at(forms, index).upper()
            if form_type not in self.forms:
                continue
            considered_filings += 1
            if considered_filings > self.max_filings_per_company:
                break
            source_record_id = self._source_record_id(accession_number)
            if source_record_id in known_source_record_ids:
                continue
            primary_document = self._value_at(primary_documents, index)
            if not primary_document:
                continue
            filing_sections = self._sections(self._value_at(items, index))
            filing_time = self._filing_time(
                self._value_at(accepted, index),
                self._value_at(filing_dates, index),
            )
            filing_url = self._filing_directory_url(company["cik"], accession_number)
            primary_document_url = f"{filing_url}{primary_document}"
            document_text = self._document_text(primary_document_url)
            filings.append(
                SourceIngestedFiling(
                    source_record_id=source_record_id,
                    source_name=self.source_name,
                    connector_type=self.connector_type,
                    ticker=company["symbol"],
                    cik=company["cik"],
                    accession_number=accession_number,
                    company=company["company"],
                    form_type=form_type,
                    published_at=filing_time,
                    filing_time=filing_time,
                    source_url=filing_url,
                    filing_url=filing_url,
                    primary_document_url=primary_document_url,
                    filing_sections=filing_sections,
                    headline=self._headline(company, form_type, filing_sections),
                    ingested_at=self._clock(),
                    metadata={"document_text": document_text},
                )
            )
        return filings

    def _document_text(self, url: str) -> str:
        text = self._fetcher(url, self._headers(url), self.timeout_seconds)
        stripped = _html_to_text(text)
        return stripped[:12000]

    def _get_json(self, url: str) -> dict[str, Any]:
        text = self._fetcher(url, self._headers(url), self.timeout_seconds)
        payload = json.loads(text)
        return payload if isinstance(payload, dict) else {}

    def _fetch_text(self, url: str, headers: dict[str, str], timeout: int) -> str:
        for attempt in range(self.max_retries + 1):
            self._respect_rate_limit()
            request = urllib.request.Request(url, headers=headers)
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    body = cast(bytes, response.read())
                    encoding = response.headers.get("Content-Encoding", "")
                    if "gzip" in encoding:
                        body = gzip.decompress(body)
                    elif "deflate" in encoding:
                        body = zlib.decompress(body)
                    return body.decode("utf-8", errors="replace")
            except urllib.error.HTTPError as exc:
                if exc.code not in {429, 500, 502, 503, 504} or attempt >= self.max_retries:
                    raise
                retry_after = exc.headers.get("Retry-After")
                delay = float(retry_after) if retry_after and retry_after.isdigit() else 2**attempt
                time.sleep(delay)
            except urllib.error.URLError:
                if attempt >= self.max_retries:
                    raise
                time.sleep(2**attempt)
        raise RuntimeError(f"SEC EDGAR request failed after retries: {url}")

    def _respect_rate_limit(self) -> None:
        minimum_interval = 1.0 / self.max_requests_per_second
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < minimum_interval:
            time.sleep(minimum_interval - elapsed)
        self._last_request_at = time.monotonic()

    def _headers(self, url: str) -> dict[str, str]:
        host = "data.sec.gov" if "data.sec.gov" in url else "www.sec.gov"
        return {
            "User-Agent": self.user_agent,
            "Accept-Encoding": "gzip, deflate",
            "Host": host,
        }

    def _body_from_filing(self, filing: SourceIngestedFiling) -> str:
        sections = ", ".join(filing.filing_sections) if filing.filing_sections else "not specified"
        document_text = str(filing.metadata.get("document_text", ""))
        return normalise_whitespace(
            " ".join(
                [
                    f"SEC EDGAR Form {filing.form_type} current report filing.",
                    f"Company: {filing.company}.",
                    f"Ticker: {filing.ticker}.",
                    f"CIK: {filing.cik}.",
                    f"Accession number: {filing.accession_number}.",
                    f"Filing sections: {sections}.",
                    document_text,
                ]
            )
        )

    def _headline(
        self,
        company: dict[str, str],
        form_type: str,
        filing_sections: list[str],
    ) -> str:
        sections = f" ({', '.join(filing_sections)})" if filing_sections else ""
        return f"{company['company']} files Form {form_type}{sections} with SEC EDGAR"

    def _submissions_url(self, cik: str) -> str:
        return f"{self.base_url}/submissions/CIK{cik}.json"

    def _filing_directory_url(self, cik: str, accession_number: str) -> str:
        compact = accession_number.replace("-", "")
        cik_int = str(int(cik))
        return f"{self.archives_base_url}/{cik_int}/{compact}/"

    def _source_record_id(self, accession_number: str) -> str:
        return f"{self.connector_type}:{accession_number}"

    def _normalise_cik(self, cik: str) -> str:
        digits = re.sub(r"\D", "", cik)
        return digits.zfill(10) if digits else ""

    def _column(self, payload: dict[str, Any], name: str) -> list[Any]:
        values = payload.get(name, [])
        return values if isinstance(values, list) else []

    def _value_at(self, values: list[Any], index: int) -> str:
        if index >= len(values):
            return ""
        value = values[index]
        return "" if value is None else str(value)

    def _sections(self, value: str) -> list[str]:
        return [section.strip() for section in value.split(",") if section.strip()]

    def _filing_time(self, accepted_at: str, filing_date: str) -> datetime:
        if accepted_at:
            normalised = accepted_at.replace("Z", "+00:00")
            try:
                return to_utc(datetime.fromisoformat(normalised))
            except ValueError:
                pass
        if filing_date:
            try:
                return datetime.fromisoformat(filing_date).replace(tzinfo=UTC)
            except ValueError:
                pass
        return self._clock()


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style"}:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style"} and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self._parts.append(data)

    def text(self) -> str:
        return normalise_whitespace(" ".join(self._parts))


def _html_to_text(value: str) -> str:
    parser = _TextExtractor()
    parser.feed(value)
    text = parser.text()
    return text or normalise_whitespace(re.sub(r"<[^>]+>", " ", value))
