from __future__ import annotations

from typing import Any

from .providers.alpaca import AlpacaMarketDataProvider
from .providers.base import ProviderError
from .providers.analysts import NotConfiguredAnalystProvider
from .providers.fx import NotConfiguredFXProvider
from .providers.index_data import NotConfiguredIndexDataProvider
from .providers.macro import NotConfiguredMacroProvider
from .providers.mock import FixtureAnalystProvider, FixtureFXProvider, FixtureMacroProvider, FixtureNewsProvider, FixtureUniverseProvider, MockMarketDataProvider
from .providers.news import NotConfiguredNewsProvider
from .readiness import ProviderBundle


def build_provider_bundle(config: dict[str, Any], now=None) -> ProviderBundle:
    provider = config.get("data", {}).get("provider", "mock")
    mode = config.get("mode", "development")
    if provider == "mock":
        return ProviderBundle(
            market_data=MockMarketDataProvider(now=now),
            universe=FixtureUniverseProvider(),
            analysts=FixtureAnalystProvider(),
            news=FixtureNewsProvider(),
            macro=FixtureMacroProvider(),
            index_data=NotConfiguredIndexDataProvider(),
            fx=FixtureFXProvider(),
        )
    if provider == "alpaca":
        use_dev_fixtures = mode == "development"
        try:
            market_data = AlpacaMarketDataProvider(feed=config.get("data", {}).get("alpaca_feed", "iex"))
        except ProviderError as ex:
            market_data = NotConfiguredMarketDataProvider(str(ex))
        return ProviderBundle(
            market_data=market_data,
            universe=FixtureUniverseProvider() if use_dev_fixtures else NotConfiguredUniverseProvider(),
            analysts=FixtureAnalystProvider() if use_dev_fixtures else NotConfiguredAnalystProvider(),
            news=FixtureNewsProvider() if use_dev_fixtures else NotConfiguredNewsProvider(),
            macro=FixtureMacroProvider() if use_dev_fixtures else NotConfiguredMacroProvider(),
            index_data=NotConfiguredIndexDataProvider(),
            fx=FixtureFXProvider() if use_dev_fixtures else NotConfiguredFXProvider(),
        )
    raise ValueError(f"Proveedor Alpha no soportado: {provider}")


class NotConfiguredUniverseProvider:
    name = "not_configured"

    def list_metadata(self):
        return []


class NotConfiguredMarketDataProvider:
    name = "not_configured"

    def __init__(self, reason: str = "market data no configurado"):
        self.reason = reason

    def latest_quote(self, symbol: str):
        raise ProviderError(self.reason)

    def intraday_bars(self, symbol: str, timeframe: str = "1Min", limit: int = 120):
        raise ProviderError(self.reason)
