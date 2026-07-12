from __future__ import annotations

from datetime import datetime

from news_intelligence.models import (
    Direction,
    EventStatus,
    EventType,
    InstrumentNewsImpact,
    InstrumentRef,
    NewsEvent,
    NewsEventCluster,
    NewsSignal,
    SignalClassification,
    SignalComposition,
    SignalDecision,
    SignalDirection,
    SignalEvidence,
    SignalMetrics,
    SignalRisk,
    SignalStrength,
    StrategyRole,
)
from news_intelligence.scoring.freshness import FreshnessScorer
from news_intelligence.utils import clamp, stable_hash


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
        composition = self._composition(event, impact, freshness)
        risk = self._risk(event, cluster)
        signal_score = self._signal_score(composition, risk)
        signal_direction = self._signal_direction(impact)
        can_trigger = (
            StrategyRole.CATALYST in event.strategy_roles
            and abs(signal_score) >= 55
            and event.analysis.confidence >= 0.65
            and event.analysis.quality >= 0.7
            and event.event_status != EventStatus.UNCONFIRMED
            and event.event_type != EventType.RUMOUR_UNCONFIRMED
            and not event.contradictions_detected
        )
        return NewsSignal(
            signal_id=stable_hash(impact.impact_id, cluster.cluster_id, prefix="sig_"),
            collector_id=f"news:{impact.symbol}:{generated_at.strftime('%Y%m%dT%H%M%SZ')}",
            event_id=event.event_id,
            cluster_id=cluster.cluster_id,
            instrument=InstrumentRef(symbol=impact.symbol),
            signal=SignalMetrics(
                signal_score=signal_score,
                direction=signal_direction,
                directional_strength=impact.directional_strength,
                confidence=impact.confidence,
                quality=impact.quality,
                freshness=freshness,
                strength=self._strength(signal_score),
                time_horizon=impact.time_horizon,
            ),
            classification=SignalClassification(
                strategy_role=event.strategy_roles,
                redundancy_cluster=event.lineage.event_group,
                causal_cluster=event.event_id,
                applicable_regimes=self._applicable_regimes(event),
            ),
            composition=composition,
            risk=risk,
            roles=event.strategy_roles,
            evidence=SignalEvidence(
                event_ids=cluster.event_ids,
                event_count=event_count,
                independent_source_count=cluster.independent_source_count,
                primary_source_present=primary_source_present,
                article_count=cluster.article_count,
                duplicate_count=cluster.duplicate_count,
                update_count=cluster.update_count,
            ),
            decision=SignalDecision(
                suggested_action=signal_direction,
                can_trigger_trade=can_trigger,
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

    def _composition(
        self,
        event: NewsEvent,
        impact: InstrumentNewsImpact,
        freshness: float,
    ) -> SignalComposition:
        return SignalComposition(
            directional_impact=impact.directional_strength,
            historical_reliability=event.historical_calibration.historical_reliability,
            source_credibility=event.source.source_credibility,
            surprise=event.analysis.surprise,
            novelty=event.analysis.novelty,
            entity_relevance=impact.relevance,
            freshness_decay=freshness,
            regime_compatibility=0.85,
        )

    def _risk(self, event: NewsEvent, cluster: NewsEventCluster) -> SignalRisk:
        return SignalRisk(
            rumour_risk=0.35
            if (
                event.event_status == EventStatus.UNCONFIRMED
                or event.event_type == EventType.RUMOUR_UNCONFIRMED
            )
            else 0.0,
            contradiction_risk=0.45
            if (event.contradictions_detected or cluster.contradictions_detected)
            else 0.0,
            scheduled_event_risk=0.25 if event.event_type == EventType.SCHEDULED_EVENT else 0.0,
            reversal_risk=0.12 if event.content_quality.is_opinion else 0.08,
            confounding_event_risk=0.05 if cluster.update_count > 0 else 0.02,
        )

    def _signal_score(self, composition: SignalComposition, risk: SignalRisk) -> float:
        quality_adjustment = (
            composition.source_credibility
            * max(composition.novelty, 0.2)
            * max(composition.historical_reliability, 0.35)
        )
        context_adjustment = composition.freshness_decay * composition.regime_compatibility
        risk_adjustment = max(
            0.0,
            1.0
            - risk.rumour_risk
            - risk.contradiction_risk
            - risk.confounding_event_risk
            - risk.reversal_risk
            - risk.scheduled_event_risk,
        )
        score = (
            100
            * composition.directional_impact
            * max(composition.surprise, 0.15)
            * quality_adjustment
            * context_adjustment
            * risk_adjustment
        )
        return round(clamp(score, lower=-100.0, upper=100.0), 2)

    def _strength(self, signal_score: float) -> SignalStrength:
        if signal_score >= 70:
            return SignalStrength.STRONG_BULLISH
        if signal_score >= 40:
            return SignalStrength.BULLISH
        if signal_score >= 15:
            return SignalStrength.WEAK_BULLISH
        if signal_score <= -70:
            return SignalStrength.STRONG_BEARISH
        if signal_score <= -40:
            return SignalStrength.BEARISH
        if signal_score <= -15:
            return SignalStrength.WEAK_BEARISH
        return SignalStrength.NEUTRAL

    def _applicable_regimes(self, event: NewsEvent) -> list[str]:
        regimes = ["EVENT_DRIVEN"]
        if event.analysis.surprise >= 0.55:
            regimes.append("HIGH_VOLATILITY")
        if event.analysis.expected_persistence != "intraday":
            regimes.append("TRENDING")
        return regimes
