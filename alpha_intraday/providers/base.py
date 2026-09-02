from __future__ import annotations

from typing import Protocol

from alpha_intraday.models import AnalystSnapshot, Bar, CatalystSnapshot, Quote, SecurityMetadata


class ProviderError(RuntimeError):
    pass


class EntitlementError(ProviderError):
    pass


class RateLimitError(ProviderError):
    pass


class MarketDataProvider(Protocol):
    name: str

    def latest_quote(self, symbol: str) -> Quote:
        ...

    def intraday_bars(self, symbol: str, timeframe: str = "1Min", limit: int = 120) -> list[Bar]:
        ...


class UniverseProvider(Protocol):
    name: str

    def list_metadata(self) -> list[SecurityMetadata]:
        ...


class AnalystProvider(Protocol):
    name: str

    def snapshot(self, symbol: str) -> AnalystSnapshot | None:
        ...


class NewsProvider(Protocol):
    name: str

    def latest_catalyst(self, symbol: str) -> CatalystSnapshot | None:
        ...


class MacroProvider(Protocol):
    name: str

    def snapshot(self) -> dict:
        ...


class IndexDataProvider(Protocol):
    name: str

    def snapshot(self) -> dict:
        ...


class FXProvider(Protocol):
    name: str

    def eurusd(self) -> tuple[float | None, str]:
        ...


class StorageProvider(Protocol):
    name: str

    def save_snapshot(self, payload: dict) -> None:
        ...
