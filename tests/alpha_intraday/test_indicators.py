from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from alpha_intraday.indicators import atr, ema, gap_pct, macd, opening_range, regular_session_vwap, relative_strength_return, resample_ohlcv, rsi, rvol_same_minute, sma, vwap


def sample_df(rows=30, hour=9, minute=30):
    start = datetime(2026, 7, 8, hour, minute, tzinfo=ZoneInfo("America/New_York"))
    idx = [start + timedelta(minutes=i) for i in range(rows)]
    return pd.DataFrame(
        {
            "open": [100 + i for i in range(rows)],
            "high": [101 + i for i in range(rows)],
            "low": [99 + i for i in range(rows)],
            "close": [100.5 + i for i in range(rows)],
            "volume": [1000 + i * 10 for i in range(rows)],
        },
        index=idx,
    )


def test_daily_indicators():
    s = pd.Series(range(1, 60))
    assert round(sma(s, 50).iloc[-1], 1) == 34.5
    assert ema(s, 20).iloc[-1] > ema(s, 50).iloc[-1]
    assert rsi(s, 14).iloc[-1] == 100
    _, _, hist = macd(s)
    assert hist.iloc[-1] >= 0


def test_intraday_indicators_vwap_resample_or():
    df = sample_df()
    assert atr(df, 14).iloc[-1] > 0
    assert vwap(df).iloc[-1] > df["low"].iloc[0]
    assert len(resample_ohlcv(df, "5min")) == 6
    assert opening_range(df, 5, now=datetime(2026, 7, 8, 9, 45, tzinfo=ZoneInfo("America/New_York")))["complete"] is True
    assert opening_range(df.head(10), 15, now=datetime(2026, 7, 8, 9, 40, tzinfo=ZoneInfo("America/New_York")))["complete"] is False


def test_gap_relative_strength_and_rvol():
    assert round(gap_pct(110, 100), 1) == 10.0
    assert relative_strength_return([100, 110], [100, 105]) > 0
    rv = rvol_same_minute(1500, [1000] * 20)
    assert rv["reliable"] is True
    assert rv["rvol"] == 1.5


def test_opening_range_ignores_premarket_and_or15_forming():
    df = sample_df(120, 8, 0)
    now = datetime(2026, 7, 8, 9, 40, tzinfo=ZoneInfo("America/New_York"))
    or5 = opening_range(df, 5, now=now)
    or15 = opening_range(df, 15, now=now)
    expected = df[(df.index >= datetime(2026, 7, 8, 9, 30, tzinfo=ZoneInfo("America/New_York"))) & (df.index < datetime(2026, 7, 8, 9, 35, tzinfo=ZoneInfo("America/New_York")))]
    assert or5["high"] == float(expected["high"].max())
    assert or15["complete"] is False


def test_regular_vwap_excludes_premarket():
    df = sample_df(120, 8, 0)
    now = datetime(2026, 7, 8, 9, 45, tzinfo=ZoneInfo("America/New_York"))
    regular = df[df.index >= datetime(2026, 7, 8, 9, 30, tzinfo=ZoneInfo("America/New_York"))]
    assert regular_session_vwap(df, now=now).iloc[-1] == vwap(regular).iloc[-1]
