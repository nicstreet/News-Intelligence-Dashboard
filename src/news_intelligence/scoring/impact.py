from __future__ import annotations

from datetime import timedelta
from typing import Any

from news_intelligence.config import NewsIntelligenceConfig
from news_intelligence.models import Direction, InstrumentNewsImpact, NewsEvent, ResolvedEntity
from news_intelligence.utils import clamp, direction_from_strength, stable_hash


class InstrumentImpactGenerator:
    def __init__(self, config: NewsIntelligenceConfig) -> None:
        self._config = config

    def impacts_for_event(self, event: NewsEvent) -> list[InstrumentNewsImpact]:
        best_entities = self._symbol_entities(event.entities)
        rule = self._config.rule_by_id(event.lineage.rule_id)
        overrides = rule.get("impact_overrides", {})
        if not isinstance(overrides, dict):
            overrides = {}

        impacts: list[InstrumentNewsImpact] = []
        for symbol, entity in best_entities.items():
            override = overrides.get(symbol, {})
            if not isinstance(override, dict):
                override = {}
            strength = self._impact_strength(event, entity, override)
            direction = (
                Direction(str(override["direction"]))
                if override.get("direction")
                else direction_from_strength(
                    strength,
                    mixed=event.analysis.direction == Direction.MIXED,
                )
            )
            confidence = float(
                override.get(
                    "confidence",
                    event.analysis.confidence * (0.78 + (0.22 * entity.relevance)),
                )
            )
            relevance = float(override.get("relevance", entity.relevance))
            reason = str(
                override.get(
                    "reason",
                    (
                        f"{symbol} affected through {entity.relationship} relationship "
                        "to the classified event."
                    ),
                )
            )
            impacts.append(
                InstrumentNewsImpact(
                    impact_id=stable_hash(event.event_id, symbol, prefix="imp_"),
                    event_id=event.event_id,
                    cluster_id=event.cluster_id,
                    symbol=symbol,
                    entity_type=entity.entity_type,
                    relationship=entity.relationship,
                    scope=entity.scope,
                    direction=direction,
                    directional_strength=round(max(-1.0, min(1.0, strength)), 4),
                    relevance=clamp(relevance),
                    confidence=clamp(confidence),
                    quality=event.analysis.quality,
                    reason=reason,
                    time_horizon=self._time_horizon(event),
                    expires_at=event.timestamps.processed_at + self._expiry_delta(event),
                    test_run_id=event.test_run_id,
                    record_environment=event.record_environment,
                )
            )
        return impacts

    def _symbol_entities(self, entities: list[ResolvedEntity]) -> dict[str, ResolvedEntity]:
        selected: dict[str, ResolvedEntity] = {}
        for entity in entities:
            if not entity.symbol:
                continue
            existing = selected.get(entity.symbol)
            if existing is None:
                selected[entity.symbol] = entity
                continue
            if (
                (entity.relationship == "direct" and existing.relationship != "direct")
                or entity.relevance > existing.relevance
            ):
                selected[entity.symbol] = entity
        return selected

    def _impact_strength(
        self,
        event: NewsEvent,
        entity: ResolvedEntity,
        override: dict[str, Any],
    ) -> float:
        if "directional_strength" in override:
            return float(override["directional_strength"])
        return (
            event.analysis.directional_strength
            * entity.relevance
            * entity.directional_multiplier
        )

    def _time_horizon(self, event: NewsEvent) -> str:
        mapping = {
            "intraday": "INTRADAY",
            "multi_day": "MULTI_DAY",
            "multi_week": "MULTI_WEEK",
        }
        return mapping[event.analysis.expected_persistence]

    def _expiry_delta(self, event: NewsEvent) -> timedelta:
        mapping = {
            "intraday": timedelta(hours=8),
            "multi_day": timedelta(days=5),
            "multi_week": timedelta(days=21),
        }
        return mapping[event.analysis.expected_persistence]
