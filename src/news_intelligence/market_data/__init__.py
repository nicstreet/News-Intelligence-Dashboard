"""Market-data adapters and calibration support."""

from news_intelligence.market_data.eodhd import EodhdMarketDataClient
from news_intelligence.market_data.service import MarketDataService
from news_intelligence.market_data.timing import EventMarketTimer

__all__ = ["EodhdMarketDataClient", "EventMarketTimer", "MarketDataService"]
