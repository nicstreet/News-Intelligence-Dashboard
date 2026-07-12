from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Score = Annotated[float, Field(ge=0.0, le=1.0)]
SignedScore = Annotated[float, Field(ge=-1.0, le=1.0)]


def utc_now() -> datetime:
    return datetime.now(UTC)


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class EventType(StrEnum):
    EARNINGS = "earnings"
    GUIDANCE = "guidance"
    PROFIT_WARNING = "profit_warning"
    CORPORATE_ACTION = "corporate_action"
    MERGER_ACQUISITION = "merger_acquisition"
    CONTRACT_COMMERCIAL = "contract_commercial"
    PRODUCT_TECHNOLOGY = "product_technology"
    MANAGEMENT_GOVERNANCE = "management_governance"
    REGULATORY_LEGAL = "regulatory_legal"
    ANALYST_MARKET_VIEW = "analyst_market_view"
    MACRO_ECONOMIC = "macro_economic"
    CENTRAL_BANK = "central_bank"
    GEOPOLITICAL = "geopolitical"
    COMMODITY_SUPPLY = "commodity_supply"
    SECTOR_INDUSTRY = "sector_industry"
    MARKET_STRUCTURE = "market_structure"
    ETF_FUND = "etf_fund"
    SCHEDULED_EVENT = "scheduled_event"
    RUMOUR_UNCONFIRMED = "rumour_unconfirmed"
    UNKNOWN = "unknown"


class ScopeType(StrEnum):
    INSTRUMENT = "instrument"
    COMPANY_GROUP = "company_group"
    ETF = "etf"
    INDUSTRY = "industry"
    SECTOR = "sector"
    COMMODITY = "commodity"
    COUNTRY = "country"
    REGION = "region"
    GLOBAL_MARKET = "global_market"


class StrategyRole(StrEnum):
    CATALYST = "CATALYST"
    CONFIRMATION = "CONFIRMATION"
    RISK_OVERLAY = "RISK_OVERLAY"
    VETO = "VETO"
    EXIT_TRIGGER = "EXIT_TRIGGER"
    HEDGE_TRIGGER = "HEDGE_TRIGGER"


class Direction(StrEnum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    MIXED = "mixed"
    NEUTRAL = "neutral"


class SignalDirection(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"
    MIXED = "MIXED"
    NEUTRAL = "NEUTRAL"


class EventStatus(StrEnum):
    CONFIRMED = "confirmed"
    UNCONFIRMED = "unconfirmed"
    DENIED = "denied"
    UPDATED = "updated"


class StageStatus(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    WARNING = "WARNING"
    FAILED = "FAILED"


class RuntimeEnvironment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class SourceConnectorState(StrEnum):
    OK = "OK"
    DEGRADED = "DEGRADED"
    DISABLED = "DISABLED"
    ERROR = "ERROR"


class ClusterItemClassification(StrEnum):
    NEW_EVENT = "NEW_EVENT"
    DUPLICATE = "DUPLICATE"
    MATERIAL_UPDATE = "MATERIAL_UPDATE"


class NewsSource(ContractModel):
    source_name: str = "Unknown Source"
    source_type: str = "unknown"
    source_url: str | None = None
    source_credibility: Score = 0.5


class SourceConnectorStatus(ContractModel):
    source_name: str
    country_or_region: str = "unknown"
    source_class: str = "unknown"
    connector_type: str
    enabled: bool
    current_status: SourceConnectorState
    last_successful_ingestion: datetime | None = None
    last_failure: str | None = None
    last_polled_at: datetime | None = None
    next_poll_after: datetime | None = None
    items_ingested: int = Field(ge=0, default=0)

    @field_validator("last_successful_ingestion", "last_polled_at", "next_poll_after")
    @classmethod
    def _normalise_datetime(cls, value: datetime | None) -> datetime | None:
        return ensure_utc(value) if value is not None else None


class SourceIngestedFiling(ContractModel):
    source_record_id: str
    source_name: str
    connector_type: str
    ticker: str
    cik: str
    accession_number: str
    company: str
    form_type: str
    filing_time: datetime
    filing_url: str
    primary_document_url: str
    filing_sections: list[str] = Field(default_factory=list)
    headline: str
    ingested_at: datetime
    raw_id: str | None = None
    event_id: str | None = None
    cluster_id: str | None = None
    test_run_id: str | None = None
    record_environment: RuntimeEnvironment = RuntimeEnvironment.DEVELOPMENT
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("filing_time", "ingested_at")
    @classmethod
    def _normalise_datetime(cls, value: datetime) -> datetime:
        return ensure_utc(value)


class SourceIngestionRun(ContractModel):
    source_name: str
    connector_type: str
    started_at: datetime
    completed_at: datetime
    fetched_count: int = Field(ge=0)
    ingested_count: int = Field(ge=0)
    skipped_count: int = Field(ge=0)
    error_count: int = Field(ge=0)
    errors: list[str] = Field(default_factory=list)
    filings: list[SourceIngestedFiling] = Field(default_factory=list)
    status: SourceConnectorStatus

    @field_validator("started_at", "completed_at")
    @classmethod
    def _normalise_datetime(cls, value: datetime) -> datetime:
        return ensure_utc(value)


class RawNewsItem(ContractModel):
    raw_id: str | None = None
    headline: str = Field(min_length=1)
    body: str | None = None
    source: NewsSource = Field(default_factory=NewsSource)
    published_at: datetime = Field(default_factory=utc_now)
    first_seen_at: datetime | None = None
    source_article_id: str | None = None
    tickers: list[str] = Field(default_factory=list)
    known_ticker: str | None = None
    country: str | None = None
    market: str | None = None
    test_run_id: str | None = None
    record_environment: RuntimeEnvironment = RuntimeEnvironment.DEVELOPMENT
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("published_at", "first_seen_at")
    @classmethod
    def _normalise_datetime(cls, value: datetime | None) -> datetime | None:
        return ensure_utc(value) if value is not None else None


class NormalisedNewsItem(ContractModel):
    raw_id: str
    normalised_id: str
    headline: str
    body: str
    normalised_text: str
    source: NewsSource
    published_at: datetime
    first_seen_at: datetime
    content_hash: str
    source_article_id: str | None = None
    detected_symbols: list[str] = Field(default_factory=list)
    country: str | None = None
    market: str | None = None
    test_run_id: str | None = None
    record_environment: RuntimeEnvironment = RuntimeEnvironment.DEVELOPMENT
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("published_at", "first_seen_at")
    @classmethod
    def _normalise_datetime(cls, value: datetime) -> datetime:
        return ensure_utc(value)


class ProcessingLineage(ContractModel):
    normaliser_version: str
    classifier_version: str
    entity_resolver_version: str
    clusterer_version: str
    scorer_version: str
    rule_id: str
    event_group: str
    raw_content_hash: str
    pipeline_version: str = "pipeline-1.0.0"


class ResolvedEntity(ContractModel):
    entity_type: ScopeType
    symbol: str | None = None
    name: str | None = None
    relationship: str = "direct"
    scope: ScopeType = ScopeType.INSTRUMENT
    relevance: Score = 1.0
    directional_multiplier: float = 1.0
    evidence: str | None = None


class NewsTimestamps(ContractModel):
    published_at: datetime
    first_seen_at: datetime
    processed_at: datetime

    @field_validator("published_at", "first_seen_at", "processed_at")
    @classmethod
    def _normalise_datetime(cls, value: datetime) -> datetime:
        return ensure_utc(value)


class NewsAnalysis(ContractModel):
    direction: Direction
    directional_strength: SignedScore
    confidence: Score
    quality: Score
    surprise: Score = 0.0
    novelty: Score = 0.0
    expected_persistence: Literal["intraday", "multi_day", "multi_week"] = "intraday"


class NewsEvent(ContractModel):
    schema_version: str = "1.0.0"
    event_id: str
    cluster_id: str = ""
    event_status: EventStatus
    event_type: EventType
    event_subtype: str
    headline: str
    summary: str
    source: NewsSource
    timestamps: NewsTimestamps
    entities: list[ResolvedEntity] = Field(default_factory=list)
    analysis: NewsAnalysis
    strategy_roles: list[StrategyRole] = Field(default_factory=list)
    lineage: ProcessingLineage
    primary_symbol: str | None = None
    contradictions_detected: bool = False
    request_id: str | None = None
    test_run_id: str | None = None
    record_environment: RuntimeEnvironment = RuntimeEnvironment.DEVELOPMENT


class ClusterArticle(ContractModel):
    event_id: str
    headline: str
    source_name: str
    published_at: datetime
    duplicate: bool
    material_update: bool
    classification: ClusterItemClassification = ClusterItemClassification.NEW_EVENT
    confirmation_status: EventStatus
    content_hash: str
    canonical_event_id: str
    test_run_id: str | None = None
    record_environment: RuntimeEnvironment = RuntimeEnvironment.DEVELOPMENT

    @field_validator("published_at")
    @classmethod
    def _normalise_datetime(cls, value: datetime) -> datetime:
        return ensure_utc(value)


class ClusterEventVersion(ContractModel):
    version: int = Field(ge=1)
    event_id: str
    event_status: EventStatus
    event_type: EventType
    event_subtype: str
    direction: Direction
    directional_strength: SignedScore
    confidence: Score
    quality: Score
    summary: str
    recorded_at: datetime
    test_run_id: str | None = None
    record_environment: RuntimeEnvironment = RuntimeEnvironment.DEVELOPMENT

    @field_validator("recorded_at")
    @classmethod
    def _normalise_datetime(cls, value: datetime) -> datetime:
        return ensure_utc(value)


class ClusterSignalSnapshot(ContractModel):
    version: int = Field(ge=1)
    signal_id: str
    event_id: str
    event_status: EventStatus
    direction: SignalDirection
    directional_strength: SignedScore
    confidence: Score
    quality: Score
    reason: str
    generated_at: datetime
    test_run_id: str | None = None
    record_environment: RuntimeEnvironment = RuntimeEnvironment.DEVELOPMENT

    @field_validator("generated_at")
    @classmethod
    def _normalise_datetime(cls, value: datetime) -> datetime:
        return ensure_utc(value)


class NewsEventCluster(ContractModel):
    schema_version: str = "1.0.0"
    cluster_id: str
    test_run_id: str | None = None
    record_environment: RuntimeEnvironment = RuntimeEnvironment.DEVELOPMENT
    canonical_event_id: str
    canonical_event: NewsEvent | None = None
    event_type: EventType
    event_group: str
    event_fingerprint: str = ""
    headline_key: str
    entity_symbols: list[str]
    article_count: int = Field(ge=1)
    duplicate_count: int = Field(ge=0)
    update_count: int = Field(ge=0, default=0)
    independent_source_count: int = Field(ge=1)
    first_publication_at: datetime
    latest_article_at: datetime | None = None
    latest_material_update_at: datetime
    event_ids: list[str]
    source_names: list[str]
    articles: list[ClusterArticle] = Field(default_factory=list)
    items: list[ClusterArticle] = Field(default_factory=list)
    signal_snapshots: list[ClusterSignalSnapshot] = Field(default_factory=list)
    event_versions: list[ClusterEventVersion] = Field(default_factory=list)
    requires_recalculation: bool = True
    contradictions_detected: bool = False

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_items(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if not data.get("articles") and data.get("items"):
                data["articles"] = data["items"]
            if not data.get("items") and data.get("articles"):
                data["items"] = data["articles"]
            if data.get("latest_article_at") is None:
                data["latest_article_at"] = data.get("latest_material_update_at")
        return data

    @model_validator(mode="after")
    def _sync_article_aliases(self) -> NewsEventCluster:
        if not self.articles and self.items:
            self.articles = self.items
        if not self.items and self.articles:
            self.items = self.articles
        if self.article_count != len(self.articles):
            raise ValueError("article_count must equal len(articles)")
        return self

    @field_validator("first_publication_at", "latest_article_at", "latest_material_update_at")
    @classmethod
    def _normalise_datetime(cls, value: datetime | None) -> datetime | None:
        return ensure_utc(value) if value is not None else None


class InstrumentNewsImpact(ContractModel):
    schema_version: str = "1.0.0"
    impact_id: str
    event_id: str
    cluster_id: str
    symbol: str
    entity_type: ScopeType
    relationship: str
    scope: ScopeType
    direction: Direction
    directional_strength: SignedScore
    relevance: Score
    confidence: Score
    quality: Score
    reason: str
    time_horizon: Literal["INTRADAY", "MULTI_DAY", "MULTI_WEEK"]
    expires_at: datetime | None = None
    test_run_id: str | None = None
    record_environment: RuntimeEnvironment = RuntimeEnvironment.DEVELOPMENT

    @field_validator("expires_at")
    @classmethod
    def _normalise_datetime(cls, value: datetime | None) -> datetime | None:
        return ensure_utc(value) if value is not None else None


class InstrumentRef(ContractModel):
    symbol: str
    exchange: str | None = None


class SignalMetrics(ContractModel):
    direction: SignalDirection
    directional_strength: SignedScore
    confidence: Score
    quality: Score
    freshness: Score
    time_horizon: Literal["INTRADAY", "MULTI_DAY", "MULTI_WEEK"]


class SignalEvidence(ContractModel):
    event_ids: list[str]
    event_count: int = Field(ge=1)
    independent_source_count: int = Field(ge=1)
    primary_source_present: bool = False
    article_count: int = Field(ge=1)
    duplicate_count: int = Field(ge=0)


class SignalDecision(ContractModel):
    can_trigger_trade: bool
    can_confirm_trade: bool
    can_veto_trade: bool
    requires_technical_confirmation: bool


class NewsSignal(ContractModel):
    schema_version: str = "1.0.0"
    collector_type: str = "news_intelligence"
    signal_id: str
    event_id: str
    cluster_id: str
    instrument: InstrumentRef
    signal: SignalMetrics
    roles: list[StrategyRole]
    evidence: SignalEvidence
    decision: SignalDecision
    generated_at: datetime
    expiry_time: datetime
    contradictions_detected: bool = False
    test_run_id: str | None = None
    record_environment: RuntimeEnvironment = RuntimeEnvironment.DEVELOPMENT

    @field_validator("generated_at", "expiry_time")
    @classmethod
    def _normalise_datetime(cls, value: datetime) -> datetime:
        return ensure_utc(value)


class PipelineError(ContractModel):
    stage: str
    summary: str
    request_id: str
    detail: str | None = None


class PipelineStage(ContractModel):
    name: str
    status: StageStatus
    payload: Any | None = None
    error: PipelineError | None = None


class NewsAnalysisResult(ContractModel):
    schema_version: str = "1.0.0"
    request_id: str
    stages: list[PipelineStage]
    raw_items: list[RawNewsItem]
    normalised_items: list[NormalisedNewsItem]
    events: list[NewsEvent]
    clusters: list[NewsEventCluster]
    impacts: list[InstrumentNewsImpact]
    signals: list[NewsSignal]
    errors: list[PipelineError] = Field(default_factory=list)
