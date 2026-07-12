from __future__ import annotations

from typing import Any

from news_intelligence.config import NewsIntelligenceConfig
from news_intelligence.models import NewsEvent, NormalisedNewsItem, ResolvedEntity, ScopeType


class InstrumentRelationshipResolver:
    def __init__(self, config: NewsIntelligenceConfig) -> None:
        self._config = config
        self.version = config.resolver_version

    def resolve(self, item: NormalisedNewsItem, event: NewsEvent) -> NewsEvent:
        entities: list[ResolvedEntity] = []
        detected_symbols = [symbol.upper() for symbol in item.detected_symbols]
        for symbol in detected_symbols:
            entities.extend(
                self._relationship_chain(symbol, evidence="matched ticker or issuer alias")
            )

        rule = self._config.rule_by_id(event.lineage.rule_id)
        for configured in rule.get("additional_entities", []):
            if isinstance(configured, dict):
                entities.append(
                    self._configured_entity(
                        configured,
                        "rule configured macro or sector exposure",
                    )
                )

        if item.country:
            entities.append(
                ResolvedEntity(
                    entity_type=ScopeType.COUNTRY,
                    name=item.country,
                    relationship="country",
                    scope=ScopeType.COUNTRY,
                    relevance=0.35,
                    directional_multiplier=0.4,
                    evidence="raw news country field",
                )
            )

        unique_entities = self._deduplicate(entities)
        primary_symbol = self._primary_symbol(detected_symbols, unique_entities)
        return event.model_copy(
            update={"entities": unique_entities, "primary_symbol": primary_symbol}
        )

    def _relationship_chain(self, symbol: str, evidence: str) -> list[ResolvedEntity]:
        instruments = self._config.instrument_relationships.get("instruments", {})
        if not isinstance(instruments, dict) or symbol not in instruments:
            return [
                ResolvedEntity(
                    entity_type=ScopeType.INSTRUMENT,
                    symbol=symbol,
                    relationship="direct",
                    scope=ScopeType.INSTRUMENT,
                    relevance=1.0,
                    evidence=evidence,
                )
            ]

        profile = instruments[symbol]
        if not isinstance(profile, dict):
            return []
        entities: list[ResolvedEntity] = []
        for relationship in profile.get("relationships", []):
            if isinstance(relationship, dict):
                entities.append(self._configured_entity(relationship, evidence))
        return entities

    def _configured_entity(self, data: dict[str, Any], evidence: str) -> ResolvedEntity:
        return ResolvedEntity(
            entity_type=ScopeType(str(data.get("entity_type", "instrument"))),
            symbol=str(data["symbol"]).upper() if data.get("symbol") else None,
            name=str(data["name"]) if data.get("name") else None,
            relationship=str(data.get("relationship", "direct")),
            scope=ScopeType(str(data.get("scope", data.get("entity_type", "instrument")))),
            relevance=float(data.get("relevance", 1.0)),
            directional_multiplier=float(
                data.get("multiplier", data.get("directional_multiplier", 1.0))
            ),
            evidence=evidence,
        )

    def _deduplicate(self, entities: list[ResolvedEntity]) -> list[ResolvedEntity]:
        best: dict[tuple[str, str, str], ResolvedEntity] = {}
        for entity in entities:
            key = (
                entity.entity_type.value,
                entity.symbol or entity.name or "",
                entity.relationship,
            )
            existing = best.get(key)
            if existing is None or entity.relevance > existing.relevance:
                best[key] = entity
        return sorted(
            best.values(),
            key=lambda entity: (
                0 if entity.relationship == "direct" else 1,
                -(entity.relevance),
                entity.symbol or entity.name or "",
            ),
        )

    def _primary_symbol(
        self,
        detected_symbols: list[str],
        entities: list[ResolvedEntity],
    ) -> str | None:
        for symbol in detected_symbols:
            if any(
                entity.symbol == symbol and entity.relationship == "direct"
                for entity in entities
            ):
                return symbol
        for entity in entities:
            if entity.symbol and entity.entity_type == ScopeType.INSTRUMENT:
                return entity.symbol
        for entity in entities:
            if entity.symbol:
                return entity.symbol
        return None
