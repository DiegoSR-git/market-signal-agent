from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from alpha_intraday.config import DEFAULT_CONFIG
from alpha_intraday.data_quality import evaluate_alpha_quality, evaluate_quote_quality, providers_consistent, spread_metrics
from alpha_intraday.models import MarketStatus, Quote


NOW = datetime(2026, 7, 8, 9, 45, tzinfo=ZoneInfo("America/New_York"))


def quote(age=1, bid=100, ask=100.05):
    return Quote("NVDA", bid, ask, 1, 1, NOW - timedelta(seconds=age), "fixture", "iex")


def test_quote_quality_blocks_stale_and_missing_bid_ask():
    assert evaluate_quote_quality(quote(age=10), NOW, DEFAULT_CONFIG)["ok"] is False
    assert evaluate_quote_quality(quote(bid=None), NOW, DEFAULT_CONFIG)["ok"] is False
    assert evaluate_quote_quality(quote(ask=None), NOW, DEFAULT_CONFIG)["ok"] is False
    assert spread_metrics(100, 100.10)["spread_pct"] > 0


def test_alpha_quality_blocks_missing_required_fields():
    result = evaluate_alpha_quality(market_status=MarketStatus.SELECTION_WINDOW, quote=quote(), now=NOW, metrics={}, analysts_count=3, config=DEFAULT_CONFIG)
    assert result["signal_allowed"] is False
    assert "NO OPERAR" in result["standard_output"]


def test_provider_conflict_blocks():
    ok = providers_consistent({"a": 100, "b": 100.05})
    bad = providers_consistent({"a": 100, "b": 102})
    assert ok["consistent"] is True
    assert bad["consistent"] is False
