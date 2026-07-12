from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from datetime import datetime
from uuid import uuid4

from news_intelligence.classification.rules import RuleBasedEventClassifier
from news_intelligence.clustering.clusterer import DeterministicClusterer
from news_intelligence.collectors.signal_builder import NewsSignalBuilder
from news_intelligence.config import NewsIntelligenceConfig, load_config
from news_intelligence.entity_resolution.resolver import InstrumentRelationshipResolver
from news_intelligence.models import (
    ClusterArticle,
    ClusterEventVersion,
    ClusterItemClassification,
    ClusterSignalSnapshot,
    Direction,
    InstrumentNewsImpact,
    NewsAnalysisResult,
    NewsEvent,
    NewsEventCluster,
    NewsSignal,
    NormalisedNewsItem,
    PipelineError,
    PipelineStage,
    RawNewsItem,
    ResolvedEntity,
    RuntimeEnvironment,
    SignalDirection,
    StageStatus,
    StrategyRole,
)
from news_intelligence.normalisation.service import NewsNormaliser
from news_intelligence.scoring.freshness import FreshnessScorer
from news_intelligence.scoring.impact import InstrumentImpactGenerator
from news_intelligence.storage import RepositoryBundle
from news_intelligence.utils import now_utc

logger = logging.getLogger(__name__)


class NewsIntelligencePipeline:
    def __init__(
        self,
        config: NewsIntelligenceConfig | None = None,
        repositories: RepositoryBundle | None = None,
        clock: Callable[[], datetime] = now_utc,
    ) -> None:
        self.config = config or load_config()
        self.clock = clock
        self.repositories = repositories or RepositoryBundle(
            self.config.root / "news_intelligence.sqlite3"
        )
        self.normaliser = NewsNormaliser(self.config, clock)
        self.classifier = RuleBasedEventClassifier(self.config, clock)
        self.resolver = InstrumentRelationshipResolver(self.config)
        self.clusterer = DeterministicClusterer()
        self.impact_generator = InstrumentImpactGenerator(self.config)
        self.freshness_scorer = FreshnessScorer(self.config)
        self.signal_builder = NewsSignalBuilder(self.freshness_scorer)

    def analyse(
        self,
        raw_items: Sequence[RawNewsItem],
        *,
        request_id: str | None = None,
        persist: bool = True,
    ) -> NewsAnalysisResult:
        correlation_id = request_id or f"req_{uuid4().hex[:12]}"
        stages: list[PipelineStage] = []
        errors: list[PipelineError] = []
        prepared_raw_items = [self._prepare_raw_item(item) for item in raw_items]

        stages.append(self._stage("Raw News", prepared_raw_items))
        normalised_items = [self.normaliser.normalise(item) for item in prepared_raw_items]
        stages.append(self._stage("Normalised News", normalised_items))

        classified_events = [
            self.classifier.classify(item, request_id=correlation_id) for item in normalised_items
        ]
        stages.append(self._stage("Event Classification", classified_events))

        events = [
            self._apply_market_reaction_stub(self.resolver.resolve(item, event), item)
            for item, event in zip(normalised_items, classified_events, strict=True)
        ]
        if any(not self._symbol_entities(event.entities) for event in events):
            errors.append(
                PipelineError(
                    stage="Entity Resolution",
                    summary="No instruments resolved for one or more events.",
                    request_id=correlation_id,
                    detail=(
                        "The event remains available, but no instrument signal can be generated."
                    ),
                )
            )
            entity_status = StageStatus.WARNING
        else:
            entity_status = StageStatus.COMPLETED
        stages.append(
            self._stage("Entity Resolution", [event.entities for event in events], entity_status)
        )

        event_by_id = {event.event_id: event for event in events}
        clusters = self.clusterer.cluster(events)
        if persist:
            clusters = self._merge_with_persisted_clusters(clusters, event_by_id)
        stages.append(self._stage("Event Cluster", clusters))

        impacts: list[InstrumentNewsImpact] = []
        signals: list[NewsSignal] = []
        cluster_by_id = {cluster.cluster_id: cluster for cluster in clusters}
        generated_at = self.clock()
        for cluster in clusters:
            if persist and not cluster.requires_recalculation:
                impacts.extend(self._stored_impacts(cluster.cluster_id))
                signals.extend(self._stored_signals(cluster))
                continue
            representative = self._representative_event(cluster, event_by_id)
            event_by_id[representative.event_id] = representative
            new_impacts = self.impact_generator.impacts_for_event(representative)
            impacts.extend(new_impacts)
            for impact in new_impacts:
                signals.append(
                    self.signal_builder.build(
                        representative,
                        cluster_by_id[impact.cluster_id],
                        impact,
                        generated_at,
                    )
                )
        self._attach_signal_snapshots(clusters, signals, event_by_id)
        stages.append(self._stage("Instrument Impacts", impacts))
        stages.append(self._stage("News Signal", signals))

        result = NewsAnalysisResult(
            request_id=correlation_id,
            stages=stages,
            raw_items=prepared_raw_items,
            normalised_items=normalised_items,
            events=events,
            clusters=clusters,
            impacts=impacts,
            signals=signals,
            errors=errors,
        )
        if persist:
            self._persist(result)
        logger.info(
            "news_analysis_completed",
            extra={
                "request_id": correlation_id,
                "event_count": len(events),
                "cluster_count": len(clusters),
                "signal_count": len(signals),
            },
        )
        return result

    def get_event(self, event_id: str) -> dict[str, object] | None:
        return self.repositories.events.get(event_id)

    def get_cluster(self, cluster_id: str) -> dict[str, object] | None:
        return self.repositories.clusters.get(cluster_id)

    def get_signals(self, symbol: str) -> list[dict[str, object]]:
        return self.repositories.signals.get_by_symbol(symbol)

    def recent_events(self, limit: int = 50) -> list[dict[str, object]]:
        return self.repositories.events.list_recent(limit)

    def _stage(
        self,
        name: str,
        payload: object,
        status: StageStatus = StageStatus.COMPLETED,
    ) -> PipelineStage:
        return PipelineStage(name=name, status=status, payload=payload)

    def _prepare_raw_item(self, item: RawNewsItem) -> RawNewsItem:
        environment = self._runtime_environment()
        if item.test_run_id:
            environment = (
                item.record_environment
                if item.record_environment != RuntimeEnvironment.PRODUCTION
                else RuntimeEnvironment.TEST
            )
        return item.model_copy(update={"record_environment": environment})

    def _runtime_environment(self) -> RuntimeEnvironment:
        try:
            return RuntimeEnvironment(self.config.environment)
        except ValueError:
            return RuntimeEnvironment.DEVELOPMENT

    def _apply_market_reaction_stub(
        self,
        event: NewsEvent,
        item: NormalisedNewsItem,
    ) -> NewsEvent:
        rejected = str(item.metadata.get("price_action_confirmation", "")).lower() == "rejected"
        text_rejected = "despite" in item.normalised_text and (
            "shares fall" in item.normalised_text or "stock falls" in item.normalised_text
        )
        if not rejected and not text_rejected:
            return event

        roles = list(
            dict.fromkeys([*event.strategy_roles, StrategyRole.RISK_OVERLAY, StrategyRole.VETO])
        )
        analysis = event.analysis.model_copy(
            update={
                "direction": Direction.BEARISH,
                "directional_strength": min(event.analysis.directional_strength, -0.24),
                "confidence": max(0.0, event.analysis.confidence * 0.75),
                "quality": max(0.0, event.analysis.quality * 0.75),
            }
        )
        return event.model_copy(
            update={
                "analysis": analysis,
                "strategy_roles": roles,
                "contradictions_detected": True,
            }
        )

    def _representative_event(
        self,
        cluster: NewsEventCluster,
        event_by_id: dict[str, NewsEvent],
    ) -> NewsEvent:
        if cluster.canonical_event is not None:
            return cluster.canonical_event
        events = [
            event_by_id[event_id]
            for event_id in cluster.event_ids
            if event_id in event_by_id
        ]
        if not events:
            raise RuntimeError(f"Cluster contains no known events: {cluster.cluster_id}")
        events.sort(key=lambda event: event.timestamps.published_at)
        denied = [event for event in events if event.event_status.value == "denied"]
        if denied:
            return denied[-1]
        confirmed = [
            event
            for event in events
            if event.event_status.value == "confirmed"
            and event.event_type.value != "rumour_unconfirmed"
        ]
        if confirmed:
            return confirmed[-1]
        return events[-1]

    def _symbol_entities(self, entities: list[ResolvedEntity]) -> list[ResolvedEntity]:
        return [entity for entity in entities if entity.symbol]

    def _merge_with_persisted_clusters(
        self,
        clusters: list[NewsEventCluster],
        current_event_by_id: dict[str, NewsEvent],
    ) -> list[NewsEventCluster]:
        merged_clusters: list[NewsEventCluster] = []
        for cluster in clusters:
            persisted = self.repositories.clusters.get(cluster.cluster_id)
            if persisted is None:
                merged_clusters.append(cluster)
                continue
            if not self._cluster_context_matches(persisted, cluster):
                merged_clusters.append(cluster)
                continue
            merged_clusters.append(
                self._merge_cluster(
                    NewsEventCluster.model_validate(persisted),
                    cluster,
                    current_event_by_id,
                )
            )
        return merged_clusters

    def _cluster_context_matches(
        self,
        persisted: dict[str, object],
        current: NewsEventCluster,
    ) -> bool:
        return (
            persisted.get("test_run_id") == current.test_run_id
            and persisted.get("record_environment") == current.record_environment.value
        )

    def _merge_cluster(
        self,
        existing: NewsEventCluster,
        current: NewsEventCluster,
        current_event_by_id: dict[str, NewsEvent],
    ) -> NewsEventCluster:
        seen_hashes = {article.content_hash for article in existing.articles}
        merged_articles = list(existing.articles)
        canonical_event = self._canonical_event(existing, current, current_event_by_id)
        event_versions = list(existing.event_versions)
        material_updates = 0
        duplicates = 0
        for item in current.articles:
            incoming_event = current_event_by_id.get(item.event_id)
            classification = self._classify_incoming_article(
                item,
                incoming_event,
                canonical_event,
                seen_hashes,
            )
            duplicate = classification == ClusterItemClassification.DUPLICATE
            material_update = classification == ClusterItemClassification.MATERIAL_UPDATE
            if duplicate:
                duplicates += 1
            if material_update and incoming_event is not None:
                material_updates += 1
                canonical_event = incoming_event
                event_versions.append(
                    self._event_version(incoming_event, version=len(event_versions) + 1)
                )
            seen_hashes.add(item.content_hash)
            merged_articles.append(
                item.model_copy(
                    update={
                        "duplicate": duplicate,
                        "material_update": material_update,
                        "classification": classification,
                        "canonical_event_id": canonical_event.event_id,
                    }
                )
            )

        merged_articles = [
            article.model_copy(update={"canonical_event_id": canonical_event.event_id})
            for article in merged_articles
        ]
        material_items = [item for item in merged_articles if item.material_update]
        latest_material_update = max(
            (item.published_at for item in material_items),
            default=existing.latest_material_update_at,
        )
        return existing.model_copy(
            update={
                "canonical_event_id": canonical_event.event_id,
                "canonical_event": canonical_event,
                "test_run_id": existing.test_run_id,
                "record_environment": existing.record_environment,
                "event_type": canonical_event.event_type,
                "entity_symbols": sorted(
                    {*existing.entity_symbols, *current.entity_symbols}
                ),
                "article_count": len(merged_articles),
                "duplicate_count": existing.duplicate_count + duplicates,
                "update_count": existing.update_count + material_updates,
                "independent_source_count": self._independent_source_count(merged_articles),
                "first_publication_at": min(
                    existing.first_publication_at,
                    current.first_publication_at,
                ),
                "latest_article_at": max(
                    existing.latest_article_at or existing.latest_material_update_at,
                    current.latest_article_at or current.latest_material_update_at,
                ),
                "latest_material_update_at": latest_material_update,
                "event_ids": list(dict.fromkeys([*existing.event_ids, *current.event_ids])),
                "source_names": sorted({*existing.source_names, *current.source_names}),
                "articles": merged_articles,
                "items": merged_articles,
                "event_versions": event_versions,
                "requires_recalculation": material_updates > 0,
                "contradictions_detected": (
                    existing.contradictions_detected or current.contradictions_detected
                ),
            }
        )

    def _independent_source_count(self, items: list[ClusterArticle]) -> int:
        return max(1, len({item.source_name for item in items}))

    def _canonical_event(
        self,
        existing: NewsEventCluster,
        current: NewsEventCluster,
        current_event_by_id: dict[str, NewsEvent],
    ) -> NewsEvent:
        if existing.canonical_event is not None:
            return existing.canonical_event
        persisted_event = self.repositories.events.get(existing.canonical_event_id)
        if persisted_event is not None:
            return NewsEvent.model_validate(persisted_event)
        if current.canonical_event is not None:
            return current.canonical_event
        event = current_event_by_id.get(current.canonical_event_id)
        if event is None:
            raise RuntimeError(f"Cannot resolve canonical event for {existing.cluster_id}")
        return event

    def _classify_incoming_article(
        self,
        article: ClusterArticle,
        incoming_event: NewsEvent | None,
        canonical_event: NewsEvent,
        seen_hashes: set[str],
    ) -> ClusterItemClassification:
        if article.content_hash in seen_hashes:
            return ClusterItemClassification.DUPLICATE
        if incoming_event is None:
            return ClusterItemClassification.DUPLICATE
        if self.clusterer._material_facts_changed(canonical_event, incoming_event):
            return ClusterItemClassification.MATERIAL_UPDATE
        return ClusterItemClassification.DUPLICATE

    def _event_version(self, event: NewsEvent, version: int) -> ClusterEventVersion:
        return ClusterEventVersion(
            version=version,
            event_id=event.event_id,
            event_status=event.event_status,
            event_type=event.event_type,
            event_subtype=event.event_subtype,
            direction=event.analysis.direction,
            directional_strength=event.analysis.directional_strength,
            confidence=event.analysis.confidence,
            quality=event.analysis.quality,
            summary=event.summary,
            recorded_at=event.timestamps.processed_at,
            test_run_id=event.test_run_id,
            record_environment=event.record_environment,
        )

    def _stored_impacts(self, cluster_id: str) -> list[InstrumentNewsImpact]:
        return [
            InstrumentNewsImpact.model_validate(impact)
            for impact in self.repositories.impacts.list_recent(500)
            if impact.get("cluster_id") == cluster_id
        ]

    def _stored_signals(self, cluster: NewsEventCluster) -> list[NewsSignal]:
        signals: list[NewsSignal] = []
        for payload in self.repositories.signals.list_recent(500):
            if payload.get("cluster_id") != cluster.cluster_id:
                continue
            signal = NewsSignal.model_validate(payload)
            signals.append(
                signal.model_copy(
                    update={
                        "evidence": signal.evidence.model_copy(
                            update={
                                "article_count": cluster.article_count,
                                "duplicate_count": cluster.duplicate_count,
                                "independent_source_count": cluster.independent_source_count,
                                "update_count": cluster.update_count,
                            }
                        )
                    }
                )
            )
        return signals

    def _attach_signal_snapshots(
        self,
        clusters: list[NewsEventCluster],
        signals: list[NewsSignal],
        event_by_id: dict[str, NewsEvent],
    ) -> None:
        signals_by_cluster: dict[str, list[NewsSignal]] = {}
        for signal in signals:
            signals_by_cluster.setdefault(signal.cluster_id, []).append(signal)

        for cluster in clusters:
            if not cluster.requires_recalculation:
                continue
            primary_signal = self._primary_signal(cluster, signals_by_cluster)
            if primary_signal is None:
                continue
            snapshots = list(cluster.signal_snapshots)
            if not snapshots and len(cluster.event_versions) > 1:
                for event_version in cluster.event_versions[:-1]:
                    snapshots.append(self._snapshot_from_event_version(event_version))
            event = event_by_id.get(primary_signal.event_id) or cluster.canonical_event
            if event is None:
                continue
            snapshots.append(
                ClusterSignalSnapshot(
                    version=len(snapshots) + 1,
                    signal_id=primary_signal.signal_id,
                    event_id=primary_signal.event_id,
                    event_status=event.event_status,
                    direction=primary_signal.signal.direction,
                    directional_strength=primary_signal.signal.directional_strength,
                    signal_score=primary_signal.signal.signal_score,
                    confidence=primary_signal.signal.confidence,
                    quality=primary_signal.signal.quality,
                    reason=event.event_subtype,
                    generated_at=primary_signal.generated_at,
                    test_run_id=event.test_run_id,
                    record_environment=event.record_environment,
                )
            )
            cluster.signal_snapshots = snapshots

    def _primary_signal(
        self,
        cluster: NewsEventCluster,
        signals_by_cluster: dict[str, list[NewsSignal]],
    ) -> NewsSignal | None:
        signals = signals_by_cluster.get(cluster.cluster_id, [])
        if not signals:
            return None
        primary_symbol = cluster.canonical_event.primary_symbol if cluster.canonical_event else None
        for signal in signals:
            if signal.instrument.symbol == primary_symbol:
                return signal
        return signals[0]

    def _snapshot_from_event_version(
        self,
        event_version: ClusterEventVersion,
    ) -> ClusterSignalSnapshot:
        direction = Direction(event_version.direction)
        if direction == Direction.BULLISH:
            signal_direction = SignalDirection.LONG
        elif direction == Direction.BEARISH:
            signal_direction = SignalDirection.SHORT
        elif direction == Direction.MIXED:
            signal_direction = SignalDirection.MIXED
        else:
            signal_direction = SignalDirection.NEUTRAL
        return ClusterSignalSnapshot(
            version=event_version.version,
            signal_id=f"snapshot_{event_version.event_id}",
            event_id=event_version.event_id,
            event_status=event_version.event_status,
            direction=signal_direction,
            directional_strength=event_version.directional_strength,
            signal_score=round(event_version.directional_strength * 100, 2),
            confidence=event_version.confidence,
            quality=event_version.quality,
            reason=event_version.event_subtype,
            generated_at=event_version.recorded_at,
            test_run_id=event_version.test_run_id,
            record_environment=event_version.record_environment,
        )

    def _persist(self, result: NewsAnalysisResult) -> None:
        for raw_item, normalised_item in zip(
            result.raw_items,
            result.normalised_items,
            strict=True,
        ):
            self.repositories.raw_news.save(raw_item.raw_id or normalised_item.raw_id, raw_item)
        for item in result.normalised_items:
            self.repositories.normalised_news.save(item.normalised_id, item)
        for event in result.events:
            self.repositories.events.save(event.event_id, event)
        for cluster in result.clusters:
            self.repositories.clusters.save(cluster.cluster_id, cluster)
        for impact in result.impacts:
            self.repositories.impacts.save(impact.impact_id, impact)
        for signal in result.signals:
            self.repositories.signals.save(signal.signal_id, signal)
