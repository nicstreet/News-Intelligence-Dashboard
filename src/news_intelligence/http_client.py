from __future__ import annotations

import urllib.error
import urllib.parse
import urllib.request
from typing import Any


def urlopen(
    request: urllib.request.Request,
    *,
    timeout: int,
    use_environment_proxy: bool = False,
) -> Any:
    if use_environment_proxy:
        return urllib.request.urlopen(request, timeout=timeout)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    return opener.open(request, timeout=timeout)


def transport_error_detail(exc: BaseException) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        return f"HTTP {exc.code}: {exc.reason}"
    if isinstance(exc, urllib.error.URLError):
        return str(exc.reason)
    return str(exc)


def redact_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(value)
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    redacted = [
        (key, "REDACTED" if key.lower() in {"api_token", "token", "apikey", "api_key"} else item)
        for key, item in query
    ]
    return urllib.parse.urlunsplit(
        parsed._replace(query=urllib.parse.urlencode(redacted))
    )
