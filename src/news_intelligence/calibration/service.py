from __future__ import annotations

from collections import defaultdict
from typing import Any

from news_intelligence.storage import RepositoryBundle
from news_intelligence.universe import FavouritesUniverseService
from news_intelligence.utils import now_utc


class HistoricalCalibrationService:
    def __init__(
        self,
        repositories: RepositoryBundle,
        universe: FavouritesUniverseService,
    ) -> None:
        self._repositories = repositories
        self._universe = universe

    def report(self, *, limit: int = 500) -> dict[str, Any]:
        favourite_symbols = set(self._universe.symbols())
        events = self._repositories.events.list_recent(limit)
        signals = self._repositories.signals.list_recent(limit)
        events_by_id = {str(event.get("event_id")): event for event in events}
        scoped_signals = [
            signal
            for signal in signals
            if self._signal_symbol(signal) in favourite_symbols
            and str(signal.get("event_id")) in events_by_id
        ]
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for signal in scoped_signals:
            event = events_by_id[str(signal.get("event_id"))]
            profile = self._profile_key(event)
            grouped[profile].append(signal)

        profiles = [
            self._profile_summary(profile, profile_signals)
            for profile, profile_signals in sorted(grouped.items())
        ]
        return {
            "schema_version": "1.0.0",
            "generated_at": now_utc().isoformat(),
            "universe_version": self._universe.universe().version,
            "favourites_count": len(favourite_symbols),
            "signal_count": len(scoped_signals),
            "outcome_windows": [
                "5m",
                "15m",
                "30m",
                "1h",
                "end_of_day",
                "1d",
                "3d",
                "5d",
                "20d",
            ],
            "outcome_status": "pending_market_data_join",
            "confounder_grades": [
                "clean_event",
                "minor_confounders",
                "major_confounders",
                "unusable",
            ],
            "profiles": profiles,
        }

    def _signal_symbol(self, signal: dict[str, Any]) -> str:
        instrument = signal.get("instrument", {})
        if not isinstance(instrument, dict):
            return ""
        return str(instrument.get("symbol", "")).upper()

    def _profile_key(self, event: dict[str, Any]) -> str:
        return "_".join(
            str(part)
            for part in [
                event.get("event_type", "unknown"),
                event.get("event_subtype", "unknown"),
                event.get("event_scope", "unknown"),
            ]
        )

    def _profile_summary(
        self,
        profile: str,
        signals: list[dict[str, Any]],
    ) -> dict[str, Any]:
        scores = [
            float(signal.get("signal", {}).get("signal_score", 0.0))
            for signal in signals
            if isinstance(signal.get("signal"), dict)
        ]
        return {
            "calibration_profile": profile,
            "sample_size": len(signals),
            "mean_signal_score": round(sum(scores) / len(scores), 4) if scores else 0.0,
            "median_abnormal_return_30m": None,
            "median_abnormal_return_1d": None,
            "median_abnormal_return_5d": None,
            "historical_reliability": None,
            "status": "requires_market_outcomes",
        }

