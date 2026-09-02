from alpha_intraday.config import DEFAULT_CONFIG
from alpha_intraday.models import CatalystSnapshot, MarketRegimeSnapshot, Regime
from alpha_intraday.scoring import build_score


def valid_metrics():
    return {
        "price": 100, "ema20": 98, "sma50": 95, "sma200": 90, "rsi_daily": 62,
        "macd_daily_hist": 0.2, "relative_strength_daily": 1, "distance_to_resistance_pct": 3,
        "price_above_vwap": True, "vwap_slope": "rising", "ema9_5m": 101, "ema20_5m": 100,
        "rsi5": 61, "macd5_hist": 0.1, "hh_hl": True, "relative_strength_spy": 0.3,
        "relative_strength_qqq": 0.2, "setup_valid": True, "average_volume": 2_000_000,
        "average_dollar_volume": 200_000_000, "spread_pct": 0.04, "rvol": 1.8,
        "rvol_reliable": True, "market_cap": 120_000_000_000, "sector_relative_strength": 0.2,
        "spy_change_pct": 0.4, "qqq_change_pct": 0.5, "binary_event_risk": False,
    }


def analysts():
    return {"analyst_count": 20, "target_median": 125, "strong_buy": 10, "buy": 6, "sell": 0, "strong_sell": 0, "recent_upgrades": 2, "recent_downgrades": 0}


def test_score_caps_and_categories():
    score = build_score(valid_metrics(), analysts(), CatalystSnapshot("NVDA", "POSITIVE", confirmed_by_price_volume=True), MarketRegimeSnapshot(Regime.BULLISH), DEFAULT_CONFIG)
    assert score.total <= 100
    assert score.risk_category.value in {"LOW", "MEDIUM", "HIGH"}


def test_score_below_78_blocks_candidate():
    m = valid_metrics()
    m["setup_valid"] = False
    m["price_above_vwap"] = False
    score = build_score(m, None, None, MarketRegimeSnapshot(Regime.BEARISH), DEFAULT_CONFIG)
    assert score.total < 78
    assert score.candidate_valid is False
