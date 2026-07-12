from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from news_intelligence.ingestion.adapters import coerce_raw_news_items
from news_intelligence.pipeline import NewsIntelligencePipeline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analyse financial news and emit signal JSON.")
    parser.add_argument(
        "--json",
        help="Raw JSON news item, list of items, or {'items': [...]} payload.",
    )
    parser.add_argument("--file", type=Path, help="Path to a JSON news payload.")
    parser.add_argument("--no-persist", action="store_true", help="Do not write results to SQLite.")
    parser.add_argument("--compact", action="store_true", help="Emit compact JSON.")
    args = parser.parse_args(argv)

    try:
        payload = _read_payload(args.json, args.file)
        raw_items = coerce_raw_news_items(payload)
        result = NewsIntelligencePipeline().analyse(raw_items, persist=not args.no_persist)
    except Exception as exc:
        print(f"news-intelligence: {exc}", file=sys.stderr)
        return 2

    if args.compact:
        print(result.model_dump_json())
    else:
        print(result.model_dump_json(indent=2))
    return 0


def _read_payload(json_arg: str | None, file_arg: Path | None) -> Any:
    if json_arg and file_arg:
        raise ValueError("Use either --json or --file, not both.")
    if json_arg:
        return json.loads(json_arg)
    if file_arg:
        with file_arg.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    return json.load(sys.stdin)


if __name__ == "__main__":
    raise SystemExit(main())
