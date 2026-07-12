from __future__ import annotations

from news_intelligence.config import NewsIntelligenceConfig
from news_intelligence.models import FavouritesUniverse


class FavouritesUniverseService:
    def __init__(self, config: NewsIntelligenceConfig) -> None:
        self._config = config

    def universe(self) -> FavouritesUniverse:
        payload = {
            "version": self._config.favourites.get("version", "favourites-unknown"),
            "description": self._config.favourites.get("description"),
            "default_benchmarks": self._config.favourites.get("default_benchmarks", {}),
            "instruments": self._config.favourite_instruments(),
        }
        return FavouritesUniverse.model_validate(payload)

    def symbols(self) -> list[str]:
        return sorted(instrument.symbol for instrument in self.universe().instruments)

