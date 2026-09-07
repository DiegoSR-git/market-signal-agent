from __future__ import annotations

from alpha_intraday.models import CatalystSnapshot


class NotConfiguredNewsProvider:
    name = "not_configured"

    def latest_catalyst(self, symbol: str) -> CatalystSnapshot | None:
        return CatalystSnapshot(symbol, "UNVERIFIED", "News provider no configurado", self.name)
