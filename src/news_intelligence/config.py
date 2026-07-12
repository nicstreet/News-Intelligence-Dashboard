from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Configuration file must contain a mapping: {path}")
    return payload


@dataclass(frozen=True)
class NewsIntelligenceConfig:
    root: Path
    event_rules: dict[str, Any]
    instrument_relationships: dict[str, Any]
    source_credibility: dict[str, Any]
    freshness_half_lives: dict[str, Any]
    runtime: dict[str, Any]
    sec_edgar: dict[str, Any]

    @property
    def rules_version(self) -> str:
        return str(self.event_rules.get("version", "rules-unknown"))

    @property
    def resolver_version(self) -> str:
        return str(self.instrument_relationships.get("version", "resolver-unknown"))

    @property
    def freshness_version(self) -> str:
        return str(self.freshness_half_lives.get("version", "freshness-unknown"))

    @property
    def source_version(self) -> str:
        return str(self.source_credibility.get("version", "sources-unknown"))

    @property
    def environment(self) -> str:
        configured = os.environ.get("NEWS_INTELLIGENCE_ENVIRONMENT")
        if configured:
            return configured
        return str(self.runtime.get("environment", "development"))

    @property
    def sec_edgar_user_agent(self) -> str:
        configured = os.environ.get("SEC_EDGAR_USER_AGENT")
        if configured:
            return configured
        return str(
            self.sec_edgar.get(
                "user_agent",
                "Asterius News Intelligence contact@example.com",
            )
        )

    def rules(self) -> list[dict[str, Any]]:
        rules = self.event_rules.get("rules", [])
        if not isinstance(rules, list):
            raise ValueError("event-rules.yaml must contain a list under 'rules'")
        return [rule for rule in rules if isinstance(rule, dict)]

    def rule_by_id(self, rule_id: str) -> dict[str, Any]:
        for rule in self.rules():
            if rule.get("id") == rule_id:
                return rule
        return {}

    def known_symbols(self) -> set[str]:
        instruments = self.instrument_relationships.get("instruments", {})
        if not isinstance(instruments, dict):
            return set()
        return {str(symbol).upper() for symbol in instruments}

    def source_profile(self, source_name: str) -> dict[str, Any]:
        sources = self.source_credibility.get("sources", {})
        if isinstance(sources, dict):
            profile = sources.get(source_name)
            if isinstance(profile, dict):
                return profile
        return {}

    def source_status(self) -> list[dict[str, Any]]:
        sources = self.source_credibility.get("sources", {})
        if not isinstance(sources, dict):
            return []
        statuses: list[dict[str, Any]] = []
        for name, profile in sorted(sources.items()):
            if not isinstance(profile, dict):
                continue
            statuses.append(
                {
                    "source_name": name,
                    "country_or_region": profile.get("country_or_region", "unknown"),
                    "source_class": profile.get("source_type", "unknown"),
                    "connector_type": profile.get("connector_type", "fixture"),
                    "enabled": bool(profile.get("enabled", False)),
                    "last_successful_ingestion": profile.get("last_successful_ingestion"),
                    "last_failure": profile.get("last_failure"),
                    "items_ingested": int(profile.get("items_ingested", 0)),
                    "current_status": profile.get("status", "UNKNOWN"),
                }
            )
        return statuses


def load_config(config_dir: Path | None = None) -> NewsIntelligenceConfig:
    root = project_root()
    directory = config_dir or root / "config"
    return NewsIntelligenceConfig(
        root=root,
        event_rules=_load_yaml(directory / "event-rules.yaml"),
        instrument_relationships=_load_yaml(directory / "instrument-relationships.yaml"),
        source_credibility=_load_yaml(directory / "source-credibility.yaml"),
        freshness_half_lives=_load_yaml(directory / "freshness-half-lives.yaml"),
        runtime=_load_yaml(directory / "runtime.yaml"),
        sec_edgar=_load_yaml(directory / "sec-edgar.yaml"),
    )
