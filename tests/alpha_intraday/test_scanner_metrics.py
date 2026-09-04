from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from alpha_intraday.config import DEFAULT_CONFIG
from alpha_intraday.models import Bar, Quote, SecurityMetadata
from alpha_intraday.scanner import bars_to_df, closed_resample, metrics_from_bars
from alpha_intraday.indicators import ema, resample_ohlcv, regular_session_df


NOW = datetime(2026, 7, 8, 9, 45, tzinfo=ZoneInfo("America/New_York"))


def bars(start_hour=8, count=120):
    start = datetime(2026, 7, 8, start_hour, 0, tzinfo=ZoneInfo("America/New_York"))
    return [Bar(start + timedelta(minutes=i), 100 + i, 101 + i, 99 + i, 100.5 + i, 1000 + i) for i in range(count)]


def meta():
    return SecurityMetadata("NVDA", "NVIDIA", "NASDAQ", "COMMON_STOCK", 100_000_000_000, 2_000_000, 200_000_000)


def quote():
    return Quote("NVDA", 130, 130.05, 1, 1, NOW, "realish", "iex")


def test_metrics_do_not_invent_missing_real_data():
    metrics = metrics_from_bars("NVDA", quote(), bars(), meta(), {}, DEFAULT_CONFIG, NOW, supplied_metrics={})
    assert metrics["relative_strength_spy"] is None
    assert metrics["rvol"] is None
    assert metrics["daily_history_available"] is False


def test_5m_indicators_use_resampled_dataframe():
    metrics = metrics_from_bars("NVDA", quote(), bars(), meta(), {}, DEFAULT_CONFIG, NOW, supplied_metrics={})
    df = bars_to_df([bar for bar in bars() if bar.timestamp <= NOW])
    df_5m = closed_resample(regular_session_df(df, NOW), "5min", NOW)
    expected = float(ema(df_5m["close"], 9).iloc[-1])
    assert metrics["ema9_5m"] == expected


def test_no_future_bars_are_used():
    future = bars() + [Bar(NOW + timedelta(minutes=5), 999, 999, 999, 999, 999)]
    metrics = metrics_from_bars("NVDA", quote(), future, meta(), {}, DEFAULT_CONFIG, NOW, supplied_metrics={})
    assert metrics["bars_1m_quality"]["last_bar_timestamp"] <= NOW.isoformat()
