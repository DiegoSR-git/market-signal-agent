from __future__ import annotations

import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

from alpha_intraday.models import Bar, Quote
from alpha_intraday.providers.base import EntitlementError, ProviderError, RateLimitError


class AlpacaMarketDataProvider:
    """Minimal Alpaca data adapter.

    Uses the official stock latest quote endpoint:
    https://data.alpaca.markets/v2/stocks/{symbol}/quotes/latest
    """

    name = "alpaca"

    def __init__(self, feed: str = "iex", timeout: float = 10.0, retries: int = 2):
        self.feed = feed
        self.timeout = timeout
        self.retries = retries
        self.key = os.getenv("ALPACA_API_KEY")
        self.secret = os.getenv("ALPACA_SECRET_KEY")
        self.base_url = os.getenv("ALPACA_DATA_BASE_URL", "https://data.alpaca.markets")
        if not self.key or not self.secret:
            raise ProviderError("ALPACA_API_KEY/ALPACA_SECRET_KEY no configuradas")

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "APCA-API-KEY-ID": self.key,
            "APCA-API-SECRET-KEY": self.secret,
        }

    def _get(self, path: str, params: dict) -> dict:
        url = f"{self.base_url}{path}"
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                resp = requests.get(url, headers=self._headers(), params=params, timeout=self.timeout)
                if resp.status_code == 403:
                    raise EntitlementError(f"Alpaca entitlement/feed rejected for feed={self.feed}")
                if resp.status_code == 429:
                    if attempt < self.retries:
                        time.sleep(2 ** attempt)
                        continue
                    raise RateLimitError("Alpaca rate limit")
                resp.raise_for_status()
                return resp.json()
            except (requests.Timeout, requests.ConnectionError) as ex:
                last_error = ex
                if attempt < self.retries:
                    time.sleep(2 ** attempt)
                    continue
                raise ProviderError(f"Alpaca request failed: {ex}") from ex
        raise ProviderError(f"Alpaca request failed: {last_error}")

    def latest_quote(self, symbol: str) -> Quote:
        data = self._get(f"/v2/stocks/{symbol}/quotes/latest", {"feed": self.feed})
        raw = data.get("quote") or {}
        timestamp = raw.get("t")
        ts = datetime.fromisoformat(timestamp.replace("Z", "+00:00")).astimezone(ZoneInfo("America/New_York")) if timestamp else None
        return Quote(symbol, raw.get("bp"), raw.get("ap"), raw.get("bs"), raw.get("as"), ts, self.name, self.feed)

    def intraday_bars(self, symbol: str, timeframe: str = "1Min", limit: int = 120) -> list[Bar]:
        raise ProviderError("Historical/intraday bars adapter pendiente de configurar con endpoint verificado")
