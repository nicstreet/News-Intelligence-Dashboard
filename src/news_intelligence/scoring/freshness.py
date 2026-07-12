from __future__ import annotations

import math
from datetime import datetime

from news_intelligence.config import NewsIntelligenceConfig
from news_intelligence.models import EventType
from news_intelligence.utils import clamp


class FreshnessScorer:
    def __init__(self, config: NewsIntelligenceConfig) -> None:
        self._config = config
        self.version = config.freshness_version

    def freshness(self, event_type: EventType, published_at: datetime, now: datetime) -> float:
        age_seconds = max(0.0, (now - published_at).total_seconds())
        half_life_hours = self.half_life_hours(event_type)
        if half_life_hours <= 0:
            return 0.0
        return clamp(math.exp(-(age_seconds / (half_life_hours * 3600.0))))

    def half_life_hours(self, event_type: EventType) -> float:
        configured = self._config.freshness_half_lives.get("event_type_half_life_hours", {})
        if isinstance(configured, dict) and event_type.value in configured:
            return float(configured[event_type.value])
        return float(self._config.freshness_half_lives.get("default_half_life_hours", 24))
