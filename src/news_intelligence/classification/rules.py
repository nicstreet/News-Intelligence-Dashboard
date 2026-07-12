from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from news_intelligence.config import NewsIntelligenceConfig
from news_intelligence.models import (
    Direction,
    EventStatus,
    EventType,
    NewsAnalysis,
    NewsEvent,
    NewsTimestamps,
    NormalisedNewsItem,
    ProcessingLineage,
    StrategyRole,
)
from news_intelligence.normalisation.service import NewsNormaliser
from news_intelligence.utils import clamp, stable_hash


class RuleBasedEventClassifier:
    def __init__(
        self,
        config: NewsIntelligenceConfig,
        clock: Callable[[], datetime],
    ) -> None:
        self._config = config
        self._clock = clock
        self.version = config.rules_version

    def classify(self, item: NormalisedNewsItem, request_id: str) -> NewsEvent:
        rule = self._best_rule(item.normalised_text)
        source_adjustment = 0.7 + (0.3 * item.source.source_credibility)
        confidence = clamp(float(rule.get("confidence", 0.2)) * source_adjustment)
        quality = clamp(float(rule.get("quality", 0.35)) * source_adjustment)
        if item.source.source_type in {"company", "central_bank", "regulatory", "exchange"}:
            confidence = clamp(confidence + 0.03)
            quality = clamp(quality + 0.04)

        direction = Direction(str(rule.get("direction", "neutral")))
        event_status = EventStatus(str(rule.get("event_status", "confirmed")))
        event_type = EventType(str(rule.get("event_type", "unknown")))
        rule_id = str(rule.get("id", "unknown"))
        event_group = str(rule.get("event_group", event_type.value))
        return NewsEvent(
            event_id=stable_hash(
                rule_id,
                item.content_hash,
                item.source_article_id,
                item.source.source_name,
                item.raw_id,
                prefix="evt_",
            ),
            event_status=event_status,
            event_type=event_type,
            event_subtype=str(rule.get("event_subtype", "unknown")),
            headline=item.headline,
            summary=self._summary(item),
            source=item.source,
            timestamps=NewsTimestamps(
                published_at=item.published_at,
                first_seen_at=item.first_seen_at,
                processed_at=self._clock(),
            ),
            analysis=NewsAnalysis(
                direction=direction,
                directional_strength=float(rule.get("directional_strength", 0.0)),
                confidence=confidence,
                quality=quality,
                surprise=float(rule.get("surprise", 0.0)),
                novelty=float(rule.get("novelty", 0.0)),
                expected_persistence=str(rule.get("expected_persistence", "intraday")),
            ),
            strategy_roles=[
                StrategyRole(str(role)) for role in rule.get("roles", ["RISK_OVERLAY"])
            ],
            lineage=ProcessingLineage(
                normaliser_version=NewsNormaliser.version,
                classifier_version=self.version,
                entity_resolver_version=self._config.resolver_version,
                clusterer_version="clusterer-1.0.0",
                scorer_version=self._config.freshness_version,
                rule_id=rule_id,
                event_group=event_group,
                raw_content_hash=item.content_hash,
            ),
            contradictions_detected=bool(rule.get("contradictions_detected", False)),
            request_id=request_id,
            test_run_id=item.test_run_id,
            record_environment=item.record_environment,
        )

    def _best_rule(self, text: str) -> dict[str, Any]:
        matches: list[tuple[int, int, dict[str, Any]]] = []
        fallback: dict[str, Any] | None = None
        for rule in self._config.rules():
            if rule.get("id") == "unknown":
                fallback = rule
                continue
            matched_terms = self._match_count(text, rule)
            if matched_terms >= 0:
                matches.append((int(rule.get("priority", 0)), matched_terms, rule))
        if not matches:
            if fallback is None:
                raise RuntimeError("No fallback classification rule configured.")
            return fallback
        matches.sort(key=lambda entry: (entry[0], entry[1]), reverse=True)
        return matches[0][2]

    def _match_count(self, text: str, rule: dict[str, Any]) -> int:
        match = rule.get("match", {})
        if not isinstance(match, dict):
            return -1
        all_terms = [str(term).lower() for term in match.get("all", [])]
        any_terms = [str(term).lower() for term in match.get("any", [])]
        exclude_terms = [str(term).lower() for term in match.get("exclude", [])]
        if any(term and term in text for term in exclude_terms):
            return -1
        if any(term and term not in text for term in all_terms):
            return -1
        if any_terms and not any(term and term in text for term in any_terms):
            return -1
        return sum(1 for term in [*all_terms, *any_terms] if term and term in text)

    def _summary(self, item: NormalisedNewsItem) -> str:
        if item.body:
            first_sentence = item.body.split(".")[0].strip()
            if first_sentence:
                return first_sentence[:360]
        return item.headline
