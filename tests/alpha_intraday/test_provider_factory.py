from unittest.mock import patch

from alpha_intraday.config import DEFAULT_CONFIG, load_config
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


def test_alpaca_without_credentials_becomes_not_configured():
    with patch.dict("os.environ", {}, clear=True):
        bundle = build_provider_bundle(cfg("alpaca"))
    assert provider_health(bundle)["market_data"] == "NOT_CONFIGURED"


def test_production_with_fixture_or_not_configured_is_not_ready():
    bundle = build_provider_bundle(cfg("mock", mode="production"))
    report = build_readiness_report(bundle, {**cfg("mock", mode="production"), "live_signals": True}, True, {"quote_available": True, "bars_available": True, "freshness_ok": True})
    assert report.production_ready is False
    assert provider_health(bundle)["market_data"] == "FIXTURE"


def test_provider_health_blocks_observed_provider_errors():
    bundle = build_provider_bundle(cfg("mock"))
    health = provider_health(bundle, {"market_data": ["NVDA bars: timeout"]})
    assert health["market_data"] == "BLOCKED"


@patch.dict("os.environ", {"ALPACA_API_KEY": "k", "ALPACA_SECRET_KEY": "s"})
def test_production_requires_news_index_and_latest_trade():
    config = cfg("alpaca", mode="production")
    config["data"]["alpaca_feed"] = "sip"
    bundle = build_provider_bundle(config)
    report = build_readiness_report(
        bundle,
        config,
        True,
        {"quote_available": True, "latest_trade_available": False, "bars_available": True, "freshness_ok": True, "index_data_verified": False},
    )
    failed = {check.name for check in report.checks if check.status.value != "PASS"}
    assert report.production_ready is False
    assert "latest_trade_available" in failed
    assert "news_catalyst_provider_real" in failed
    assert "index_data_critical" in failed
    assert "index_data_verified" in failed


def test_alpha_data_provider_env_overrides_config(tmp_path):
    path = tmp_path / "alpha.yml"
    path.write_text("data:\n  provider: mock\n", encoding="utf-8")
    with patch.dict("os.environ", {"ALPHA_DATA_PROVIDER": "alpaca"}):
        assert load_config(path)["data"]["provider"] == "alpaca"
