from __future__ import annotations


class NotConfiguredIndexDataProvider:
    name = "not_configured"

    def snapshot(self) -> dict:
        return {
            "sp500_index": None,
            "nasdaq100_index": None,
            "actual_index_verified": False,
            "spy_proxy_available": False,
            "qqq_proxy_available": False,
        }
