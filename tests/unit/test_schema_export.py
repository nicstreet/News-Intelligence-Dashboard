from __future__ import annotations

from news_intelligence.schemas.export import public_json_schemas


def test_public_json_schema_export_contains_required_contracts() -> None:
    schemas = public_json_schemas()

    for name in [
        "RawNewsItem",
        "NormalisedNewsItem",
        "NewsSource",
        "ResolvedEntity",
        "NewsEvent",
        "NewsEventCluster",
        "InstrumentNewsImpact",
        "NewsSignal",
        "ProcessingLineage",
        "SourceConnectorStatus",
        "SourceIngestedFiling",
        "SourceIngestionRun",
    ]:
        assert name in schemas
        assert schemas[name]["type"] == "object"
