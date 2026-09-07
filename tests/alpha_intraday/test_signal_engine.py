from datetime import datetime
from zoneinfo import ZoneInfo

from alpha_intraday.config import DEFAULT_CONFIG
from alpha_intraday.providers.index_data import NotConfiguredIndexDataProvider
from alpha_intraday.providers.mock import FixtureAnalystProvider, FixtureFXProvider, FixtureMacroProvider, FixtureNewsProvider, FixtureUniverseProvider, MockMarketDataProvider
from alpha_intraday.readiness import ProviderBundle
from alpha_intraday.signal_engine import run_alpha


class OneSymbolQuoteFails(MockMarketDataProvider):
    def latest_quote(self, symbol):
        if symbol == "NVDA":
            raise TimeoutError("quote timeout")
        return super().latest_quote(symbol)


def test_development_blocks_live_signal_and_short_is_impossible(tmp_path):
    config = dict(DEFAULT_CONFIG)
    config["output"] = {"snapshot": str(tmp_path / "snapshot.json"), "dashboard_dir": str(tmp_path / "docs")}
    snapshot = run_alpha(config, now=datetime(2026, 7, 8, 9, 45, tzinfo=ZoneInfo("America/New_York")))
    assert snapshot.data_mode.value == "development"
    assert snapshot.signal_allowed is False
    assert all(c.setup.status.value != "READY_SHORT" for c in snapshot.candidates)
    assert (tmp_path / "snapshot.json").exists()
    assert (tmp_path / "docs" / "index.html").exists()


def test_symbol_provider_failure_blocks_health_without_crashing(tmp_path):
    now = datetime(2026, 7, 8, 9, 45, tzinfo=ZoneInfo("America/New_York"))
    config = dict(DEFAULT_CONFIG)
    config["output"] = {"snapshot": str(tmp_path / "snapshot.json"), "dashboard_dir": str(tmp_path / "docs")}
    providers = ProviderBundle(
        market_data=OneSymbolQuoteFails(now=now),
        universe=FixtureUniverseProvider(),
        analysts=FixtureAnalystProvider(),
        news=FixtureNewsProvider(),
        macro=FixtureMacroProvider(),
        index_data=NotConfiguredIndexDataProvider(),
        fx=FixtureFXProvider(),
    )
    snapshot = run_alpha(config, providers=providers, now=now)
    assert snapshot.provider_health["market_data"] == "BLOCKED"
    assert snapshot.signal_allowed is False
    assert any("market_data BLOCKED" in reason for reason in snapshot.blocking_reasons)
