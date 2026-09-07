from __future__ import annotations


class NotConfiguredMacroProvider:
    name = "not_configured"

    def snapshot(self) -> dict:
        return {"spy_change_pct": None, "qqq_change_pct": None, "vix": None, "us10y": None}
