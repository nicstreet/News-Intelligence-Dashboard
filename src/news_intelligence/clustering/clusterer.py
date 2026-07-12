from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from news_intelligence.models import (
    ClusterArticle,
    ClusterEventVersion,
    ClusterItemClassification,
    NewsEvent,
    NewsEventCluster,
    NormalisedNewsItem,
)
from news_intelligence.utils import headline_key, jaccard_similarity, stable_hash, token_set

MATERIAL_UPDATE_TERMS = {
    "approval with restrictions",
    "company denial",
    "confirms",
    "confirmed",
    "denies",
    "final confirmed",
    "formal offer",
    "offer price",
    "preliminary takeover approach",
    "production suspended",
    "regulator confirmation",
    "restricted approval",
    "suspended production",
}


def classify_cluster_item(
    incoming: NormalisedNewsItem,
    cluster: NewsEventCluster,
) -> ClusterItemClassification:
    if any(article.content_hash == incoming.content_hash for article in cluster.articles):
        return ClusterItemClassification.DUPLICATE

    incoming_symbols = set(incoming.detected_symbols)
    cluster_symbols = set(cluster.entity_symbols)
    if incoming_symbols and cluster_symbols and not incoming_symbols.intersection(cluster_symbols):
        return ClusterItemClassification.NEW_EVENT

    if any(term in incoming.normalised_text for term in MATERIAL_UPDATE_TERMS):
        return ClusterItemClassification.MATERIAL_UPDATE

    return ClusterItemClassification.DUPLICATE


@dataclass
class _ClusterDraft:
    event_group: str
    primary_symbol: str | None
    event_fingerprint: str
    events: list[NewsEvent] = field(default_factory=list)


class DeterministicClusterer:
    version = "clusterer-1.0.0"

    def cluster(self, events: list[NewsEvent]) -> list[NewsEventCluster]:
        drafts: list[_ClusterDraft] = []
        for event in sorted(events, key=lambda candidate: candidate.timestamps.published_at):
            draft = self._find_cluster(drafts, event)
            if draft is None:
                draft = _ClusterDraft(
                    event_group=event.lineage.event_group,
                    primary_symbol=event.primary_symbol,
                    event_fingerprint=self._event_fingerprint(event),
                )
                drafts.append(draft)
            draft.events.append(event)

        clusters = [self._materialise(draft) for draft in drafts]
        for cluster in clusters:
            for event in events:
                if event.event_id in cluster.event_ids:
                    event.cluster_id = cluster.cluster_id
        return clusters

    def _find_cluster(self, drafts: list[_ClusterDraft], event: NewsEvent) -> _ClusterDraft | None:
        for draft in drafts:
            if draft.event_group != event.lineage.event_group:
                continue
            if draft.event_fingerprint != self._event_fingerprint(event):
                continue
            if (
                draft.primary_symbol
                and event.primary_symbol
                and draft.primary_symbol != event.primary_symbol
            ):
                continue
            if any(self._same_underlying_event(existing, event) for existing in draft.events):
                return draft
        return None

    def _same_underlying_event(self, left: NewsEvent, right: NewsEvent) -> bool:
        left_time = left.timestamps.published_at
        right_time = right.timestamps.published_at
        if abs(left_time - right_time) > timedelta(hours=48):
            return False
        left_symbols = {entity.symbol for entity in left.entities if entity.symbol}
        right_symbols = {entity.symbol for entity in right.entities if entity.symbol}
        if left_symbols and right_symbols and not left_symbols.intersection(right_symbols):
            return False
        if self._event_fingerprint(left) != self._event_fingerprint(right):
            return False
        if (
            left.lineage.event_group == right.lineage.event_group == "merger_acquisition"
            and left.primary_symbol
            and left.primary_symbol == right.primary_symbol
        ):
            return True
        if left.lineage.raw_content_hash == right.lineage.raw_content_hash:
            return True
        similarity = jaccard_similarity(token_set(left.headline), token_set(right.headline))
        return similarity >= 0.45

    def _materialise(self, draft: _ClusterDraft) -> NewsEventCluster:
        events = sorted(draft.events, key=lambda event: event.timestamps.published_at)
        canonical_event = events[0]
        cluster_id = stable_hash(
            canonical_event.record_environment.value,
            canonical_event.test_run_id or "persistent",
            draft.event_fingerprint,
            canonical_event.timestamps.published_at.date().isoformat(),
            prefix="cluster_",
        )
        seen_hashes: set[str] = set()
        items: list[ClusterArticle] = []
        duplicate_count = 0
        update_count = 0
        event_versions = [self._event_version(canonical_event, version=1)]
        active_event = canonical_event
        latest_article_at = canonical_event.timestamps.published_at
        latest_material_update = canonical_event.timestamps.published_at
        for index, event in enumerate(events):
            latest_article_at = max(latest_article_at, event.timestamps.published_at)
            classification = self._classify_event(index, event, active_event, seen_hashes)
            duplicate = classification == ClusterItemClassification.DUPLICATE
            material_update = classification == ClusterItemClassification.MATERIAL_UPDATE
            if duplicate:
                duplicate_count += 1
            if material_update:
                update_count += 1
                latest_material_update = max(latest_material_update, event.timestamps.published_at)
                active_event = event
                event_versions.append(self._event_version(event, version=len(event_versions) + 1))
            seen_hashes.add(event.lineage.raw_content_hash)
            items.append(
                ClusterArticle(
                    event_id=event.event_id,
                    headline=event.headline,
                    source_name=event.source.source_name,
                    published_at=event.timestamps.published_at,
                    duplicate=duplicate,
                    material_update=material_update,
                    classification=classification,
                    confirmation_status=event.event_status,
                    content_hash=event.lineage.raw_content_hash,
                    canonical_event_id="",
                    test_run_id=event.test_run_id,
                    record_environment=event.record_environment,
                )
            )
        canonical_event = active_event
        items = [
            item.model_copy(update={"canonical_event_id": canonical_event.event_id})
            for item in items
        ]

        entity_symbols = sorted(
            {entity.symbol for event in events for entity in event.entities if entity.symbol}
        )
        source_names = sorted({event.source.source_name for event in events})
        return NewsEventCluster(
            cluster_id=cluster_id,
            test_run_id=canonical_event.test_run_id,
            record_environment=canonical_event.record_environment,
            canonical_event_id=canonical_event.event_id,
            canonical_event=canonical_event,
            event_type=canonical_event.event_type,
            event_group=draft.event_group,
            event_fingerprint=draft.event_fingerprint,
            headline_key=headline_key(canonical_event.headline),
            entity_symbols=entity_symbols,
            article_count=len(events),
            duplicate_count=duplicate_count,
            update_count=update_count,
            independent_source_count=max(1, len(source_names)),
            first_publication_at=events[0].timestamps.published_at,
            latest_article_at=latest_article_at,
            latest_material_update_at=latest_material_update,
            event_ids=[event.event_id for event in events],
            source_names=source_names,
            articles=items,
            items=items,
            event_versions=event_versions,
            contradictions_detected=any(event.contradictions_detected for event in events),
        )

    def _classify_event(
        self,
        index: int,
        event: NewsEvent,
        active_event: NewsEvent,
        seen_hashes: set[str],
    ) -> ClusterItemClassification:
        if index == 0:
            return ClusterItemClassification.NEW_EVENT
        if event.lineage.raw_content_hash in seen_hashes:
            return ClusterItemClassification.DUPLICATE
        if self._material_facts_changed(active_event, event):
            return ClusterItemClassification.MATERIAL_UPDATE
        return ClusterItemClassification.DUPLICATE

    def _material_facts_changed(self, existing: NewsEvent, incoming: NewsEvent) -> bool:
        if existing.event_status != incoming.event_status:
            return True
        if existing.event_type != incoming.event_type:
            return True
        if existing.event_subtype != incoming.event_subtype:
            return True
        if existing.analysis.direction != incoming.analysis.direction:
            return True
        if existing.analysis.expected_persistence != incoming.analysis.expected_persistence:
            return True
        if existing.contradictions_detected != incoming.contradictions_detected:
            return True

        existing_symbols = {entity.symbol for entity in existing.entities if entity.symbol}
        incoming_symbols = {entity.symbol for entity in incoming.entities if entity.symbol}
        if incoming_symbols and incoming_symbols != existing_symbols:
            return True

        strength_delta = abs(
            incoming.analysis.directional_strength - existing.analysis.directional_strength
        )
        return strength_delta >= 0.2

    def _event_fingerprint(self, event: NewsEvent) -> str:
        symbol = event.primary_symbol or "market"
        anchor = self._event_anchor(event)
        return f"{event.lineage.event_group}:{symbol}:{anchor}"

    def _event_anchor(self, event: NewsEvent) -> str:
        text = f"{event.headline} {event.summary}".lower()
        anchors = {
            "approval": ("approval", "restricted", "rejection", "delay"),
            "earnings": ("earnings", "guidance"),
            "mine_disruption": ("mine", "disruption", "production suspended"),
            "price_action": ("price action", "shares fall", "market rejects"),
            "rate_cut": ("rate cut", "central bank"),
            "safety_investigation": ("safety investigation", "safety probe"),
            "takeover": ("takeover", "acquisition", "bid", "approach"),
        }
        for anchor, terms in anchors.items():
            if any(term in text for term in terms):
                return anchor
        return event.event_subtype

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
