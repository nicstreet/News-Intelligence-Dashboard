from __future__ import annotations

from news_intelligence.http_client import redact_url


def test_redact_url_removes_sensitive_query_values() -> None:
    redacted = redact_url(
        "https://eodhd.com/api/news?api_token=secret&fmt=json&api_key=other"
    )

    assert "secret" not in redacted
    assert "other" not in redacted
    assert "api_token=REDACTED" in redacted
    assert "api_key=REDACTED" in redacted
    assert "fmt=json" in redacted
