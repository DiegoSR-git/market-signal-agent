from __future__ import annotations

from alpha_intraday.models import AnalystSnapshot


class NotConfiguredAnalystProvider:
    name = "not_configured"

    def snapshot(self, symbol: str) -> AnalystSnapshot | None:
        return None
