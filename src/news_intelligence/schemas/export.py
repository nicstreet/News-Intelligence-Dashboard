from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from news_intelligence.models import (
    InstrumentNewsImpact,
    NewsAnalysisResult,
    NewsEvent,
    NewsEventCluster,
    NewsSignal,
    NewsSource,
    NormalisedNewsItem,
    ProcessingLineage,
    RawNewsItem,
    ResolvedEntity,
)

PUBLIC_MODELS: tuple[type[BaseModel], ...] = (
    RawNewsItem,
    NormalisedNewsItem,
    NewsSource,
    ResolvedEntity,
    NewsEvent,
    NewsEventCluster,
    InstrumentNewsImpact,
    NewsSignal,
    ProcessingLineage,
    NewsAnalysisResult,
)


def public_json_schemas() -> dict[str, Any]:
    return {model.__name__: model.model_json_schema() for model in PUBLIC_MODELS}


def export_json_schemas(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, schema in public_json_schemas().items():
        with (output_dir / f"{name}.schema.json").open("w", encoding="utf-8") as handle:
            json.dump(schema, handle, indent=2, sort_keys=True)
            handle.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export public news intelligence JSON Schemas.")
    parser.add_argument("--output", type=Path, default=Path("schemas"))
    args = parser.parse_args(argv)
    export_json_schemas(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
