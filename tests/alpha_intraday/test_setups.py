from datetime import datetime
from zoneinfo import ZoneInfo

from alpha_intraday.config import DEFAULT_CONFIG
from alpha_intraday.models import MarketStatus, SignalStatus
from alpha_intraday.setups import evaluate_setup


NOW = datetime(2026, 7, 8, 9, 45, tzinfo=ZoneInfo("America/New_York"))


def metrics():
    return {"breakout_valid": True, "entry": 100, "stop": 99, "target1": 101.6, "target2": 102.5, "rsi5": 62, "distance_from_vwap_pct": 0.2, "atr_consumed_pct": 40}


def test_premarket_cannot_ready_long():
    plan = evaluate_setup(metrics(), MarketStatus.PREMARKET, NOW, DEFAULT_CONFIG)
    assert plan.status == SignalStatus.PRESELECTED


def test_after_1015_cannot_ready_long():
    plan = evaluate_setup(metrics(), MarketStatus.ENTRY_CLOSED, NOW, DEFAULT_CONFIG)
    assert plan.status == SignalStatus.WAIT


def test_ready_long_requires_rr_and_no_chase():
    assert evaluate_setup(metrics(), MarketStatus.SELECTION_WINDOW, NOW, DEFAULT_CONFIG).status == SignalStatus.READY_LONG
    bad = metrics()
    bad["target1"] = 100.5
    assert evaluate_setup(bad, MarketStatus.SELECTION_WINDOW, NOW, DEFAULT_CONFIG).status == SignalStatus.NO_TRADE
    chase = metrics()
    chase["rsi5"] = 81
    assert evaluate_setup(chase, MarketStatus.SELECTION_WINDOW, NOW, DEFAULT_CONFIG).status == SignalStatus.NO_TRADE
