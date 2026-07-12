from __future__ import annotations

from datetime import datetime

from news_intelligence.models import (
    Direction,
    InstrumentNewsImpact,
    InstrumentRef,
    NewsEvent,
    NewsEventCluster,
    NewsSignal,
    SignalDecision,
    SignalDirection,
    SignalEvidence,
    SignalMetrics,
    StrategyRole,
)
from news_intelligence.scoring.freshness import FreshnessScorer
from news_intelligence.utils import stable_hash


class NewsSignalBuilder:
    def __init__(self, freshness_scorer: FreshnessScorer) -> None:
        self._freshness_scorer = freshness_scorer

    def build(
        self,
        event: NewsEvent,
        cluster: NewsEventCluster,
        impact: InstrumentNewsImpact,
        generated_at: datetime,
    ) -> NewsSignal:
        freshness = self._freshness_scorer.freshness(
            event.event_type,
            event.timestamps.published_at,
            generated_at,
        )
        can_veto = StrategyRole.VETO in event.strategy_roles or (
            impact.direction == Direction.BEARISH and impact.directional_strength < -0.55
        )
        can_confirm = (
            StrategyRole.CONFIRMATION in event.strategy_roles
            and not can_veto
            and event.analysis.confidence >= 0.45
        )
        event_count = max(1, cluster.article_count - cluster.duplicate_count)
        source_type = event.source.source_type
        primary_source_present = source_type in {
            "company",
            "regulatory",
            "central_bank",
            "exchange",
        }
        return NewsSignal(
            signal_id=stable_hash(impact.impact_id, cluster.cluster_id, prefix="sig_"),
            event_id=event.event_id,
            cluster_id=cluster.cluster_id,
            instrument=InstrumentRef(symbol=impact.symbol),
            signal=SignalMetrics(
                direction=self._signal_direction(impact),
                directional_strength=impact.directional_strength,
                confidence=impact.confidence,
                quality=impact.quality,
                freshness=freshness,
                time_horizon=impact.time_horizon,
            ),
            roles=event.strategy_roles,
            evidence=SignalEvidence(
                event_ids=cluster.event_ids,
                event_count=event_count,
                independent_source_count=cluster.independent_source_count,
                primary_source_present=primary_source_present,
                article_count=cluster.article_count,
                duplicate_count=cluster.duplicate_count,
            ),
            decision=SignalDecision(
                can_trigger_trade=False,
                can_confirm_trade=can_confirm,
                can_veto_trade=can_veto,
                requires_technical_confirmation=True,
            ),
            generated_at=generated_at,
            expiry_time=impact.expires_at or generated_at,
            contradictions_detected=(
                event.contradictions_detected or cluster.contradictions_detected
            ),
            test_run_id=event.test_run_id,
            record_environment=event.record_environment,
        )

    def _signal_direction(self, impact: InstrumentNewsImpact) -> SignalDirection:
        if impact.direction == Direction.MIXED:
            return SignalDirection.MIXED
        if impact.directional_strength > 0.08:
            return SignalDirection.LONG
        if impact.directional_strength < -0.08:
            return SignalDirection.SHORT
        return SignalDirection.NEUTRAL
