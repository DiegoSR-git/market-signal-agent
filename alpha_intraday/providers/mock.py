from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from alpha_intraday.models import AnalystSnapshot, Bar, CatalystSnapshot, Quote, SecurityMetadata


class MockMarketDataProvider:
    name = "mock"

    def __init__(self, now: datetime | None = None):
        self.now = now or datetime.now(ZoneInfo("America/New_York"))

    def latest_quote(self, symbol: str) -> Quote:
        quotes = {
            "NVDA": (128.10, 128.16),
            "MSFT": (420.00, 420.08),
            "AAPL": (211.00, 211.09),
        }
        bid, ask = quotes.get(symbol, (100.00, 100.08))
        return Quote(symbol, bid, ask, 100, 100, self.now - timedelta(seconds=1), self.name, "fixture")

    def intraday_bars(self, symbol: str, timeframe: str = "1Min", limit: int = 120) -> list[Bar]:
        start = self.now.replace(hour=9, minute=30, second=0, microsecond=0)
        bars: list[Bar] = []
        price = 126.0 if symbol == "NVDA" else 100.0
        for i in range(limit):
            ts = start + timedelta(minutes=i)
            close = price + i * 0.03
            bars.append(Bar(ts, close - 0.08, close + 0.12, close - 0.18, close, 90000 + i * 700))
        return bars


class FixtureUniverseProvider:
    name = "fixture"

    def list_metadata(self) -> list[SecurityMetadata]:
        now = datetime.now(ZoneInfo("America/New_York"))
        return [
            SecurityMetadata("NVDA", "NVIDIA Corp", "NASDAQ", "COMMON_STOCK", 3_000_000_000_000, 200_000_000, 25_000_000_000, "Technology", "Semiconductors", True, True, self.name, now),
            SecurityMetadata("MSFT", "Microsoft Corp", "NASDAQ", "COMMON_STOCK", 3_100_000_000_000, 20_000_000, 8_000_000_000, "Technology", "Software", True, True, self.name, now),
            SecurityMetadata("SPY", "SPDR S&P 500 ETF", "NYSE", "ETF", 0, 70_000_000, 35_000_000_000, "ETF", "ETF", True, True, self.name, now),
        ]


class FixtureAnalystProvider:
    name = "fixture"

    def snapshot(self, symbol: str) -> AnalystSnapshot | None:
        if symbol == "NVDA":
            return AnalystSnapshot(symbol, 48, 30, 12, 5, 1, 0, 160.0, 158.0, 110.0, 190.0, True, self.name)
        if symbol == "MSFT":
            return AnalystSnapshot(symbol, 40, 20, 12, 7, 1, 0, 510.0, 505.0, 390.0, 600.0, True, self.name)
        return None


class FixtureNewsProvider:
    name = "fixture"

    def latest_catalyst(self, symbol: str) -> CatalystSnapshot | None:
        if symbol == "NVDA":
            return CatalystSnapshot(symbol, "POSITIVE", "Catalizador sintetico de fixture confirmado por volumen", self.name, confirmed_by_price_volume=True)
        return CatalystSnapshot(symbol, "NONE", "", self.name, confirmed_by_price_volume=False)


class FixtureFXProvider:
    name = "fixture"

    def eurusd(self) -> tuple[float | None, str]:
        return 1.08, self.name


class FixtureMacroProvider:
    name = "fixture"

    def snapshot(self) -> dict:
        return {"spy_change_pct": 0.35, "qqq_change_pct": 0.52, "vix": 15.2, "us10y": 4.1}
