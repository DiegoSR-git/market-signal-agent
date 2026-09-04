from unittest.mock import patch

from alpha_intraday.config import DEFAULT_CONFIG
from alpha_intraday.provider_factory import build_provider_bundle
from alpha_intraday.providers.alpaca import AlpacaMarketDataProvider
from alpha_intraday.providers.mock import MockMarketDataProvider
from alpha_intraday.readiness import build_readiness_report, provider_health


def cfg(provider, mode="development"):
    config = dict(DEFAULT_CONFIG)
    config["data"] = dict(DEFAULT_CONFIG["data"])
    config["data"]["provider"] = provider
    config["mode"] = mode
    return config


def test_provider_factory_mock_vs_alpaca():
    assert isinstance(build_provider_bundle(cfg("mock")).market_data, MockMarketDataProvider)
    with patch.dict("os.environ", {"ALPACA_API_KEY": "k", "ALPACA_SECRET_KEY": "s"}):
        assert isinstance(build_provider_bundle(cfg("alpaca")).market_data, AlpacaMarketDataProvider)


def test_production_with_fixture_or_not_configured_is_not_ready():
    bundle = build_provider_bundle(cfg("mock", mode="production"))
    report = build_readiness_report(bundle, {**cfg("mock", mode="production"), "live_signals": True}, True, {"quote_available": True, "bars_available": True, "freshness_ok": True})
    assert report.production_ready is False
    assert provider_health(bundle)["market_data"] == "FIXTURE"
