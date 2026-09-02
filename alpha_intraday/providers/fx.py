from __future__ import annotations


class NotConfiguredFXProvider:
    name = "not_configured"

    def eurusd(self) -> tuple[float | None, str]:
        return None, self.name
