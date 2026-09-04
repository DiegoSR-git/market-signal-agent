from __future__ import annotations

import numpy as np
import pandas as pd

from .market_clock import NY_TZ


def sma(series, window: int):
    return pd.Series(series, dtype="float64").rolling(window).mean()


def ema(series, span: int):
    return pd.Series(series, dtype="float64").ewm(span=span, adjust=False).mean()


def rsi(series, period: int = 14):
    s = pd.Series(series, dtype="float64")
    delta = s.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    enough_history = s.expanding().count() > period
    all_gain = (loss == 0) & enough_history
    return out.where(~all_gain, 100)


def macd(series, fast: int = 12, slow: int = 26, signal: int = 9):
    s = pd.Series(series, dtype="float64")
    macd_line = ema(s, fast) - ema(s, slow)
    signal_line = ema(macd_line, signal)
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def atr(df: pd.DataFrame, period: int = 14):
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)
    prev_close = close.shift(1)
    tr = pd.concat([(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def vwap(df: pd.DataFrame):
    typical = (df["high"].astype(float) + df["low"].astype(float) + df["close"].astype(float)) / 3
    volume = df["volume"].astype(float)
    return (typical * volume).cumsum() / volume.cumsum()


def regular_session_df(df: pd.DataFrame, now=None):
    if df.empty:
        return df
    out = df.copy()
    if out.index.tz is None:
        raise ValueError("bar timestamps deben tener timezone")
    out.index = out.index.tz_convert(NY_TZ)
    session_day = (now.astimezone(NY_TZ).date() if now is not None else out.index[-1].date())
    return out[
        (out.index.date == session_day)
        & (out.index.time >= pd.Timestamp("09:30").time())
        & (out.index.time < pd.Timestamp("16:00").time())
    ]


def historical_regular_session_df(df: pd.DataFrame, now=None):
    if df.empty:
        return df
    out = df.copy()
    if out.index.tz is None:
        raise ValueError("bar timestamps deben tener timezone")
    out.index = out.index.tz_convert(NY_TZ)
    if now is not None:
        out = out[out.index <= now.astimezone(NY_TZ)]
    return out[
        (out.index.time >= pd.Timestamp("09:30").time())
        & (out.index.time < pd.Timestamp("16:00").time())
    ]


def regular_session_vwap(df: pd.DataFrame, now=None):
    return vwap(regular_session_df(df, now=now))


def resample_ohlcv(df: pd.DataFrame, rule: str):
    return (
        df.resample(rule)
        .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
        .dropna()
    )


def opening_range(df: pd.DataFrame, minutes: int, now=None):
    if df.empty:
        return {"high": None, "low": None, "complete": False}
    regular = regular_session_df(df, now=now)
    if regular.empty:
        return {"high": None, "low": None, "complete": False}
    session_day = (now.astimezone(NY_TZ).date() if now is not None else regular.index[-1].date())
    start = pd.Timestamp.combine(session_day, pd.Timestamp("09:30").time()).tz_localize(NY_TZ)
    end = start + pd.Timedelta(minutes=minutes)
    window = regular[(regular.index >= start) & (regular.index < end)]
    complete_by_time = True if now is None else now.astimezone(NY_TZ) >= end
    return {
        "high": float(window["high"].max()) if not window.empty else None,
        "low": float(window["low"].min()) if not window.empty else None,
        "complete": complete_by_time and len(window) >= minutes,
    }


def gap_pct(current_price: float, previous_close: float):
    return ((current_price / previous_close) - 1) * 100


def relative_strength_return(stock_prices, benchmark_prices):
    stock = pd.Series(stock_prices, dtype="float64")
    bench = pd.Series(benchmark_prices, dtype="float64")
    if len(stock) < 2 or len(bench) < 2:
        return np.nan
    stock_ret = (stock.iloc[-1] / stock.iloc[0]) - 1
    bench_ret = (bench.iloc[-1] / bench.iloc[0]) - 1
    return (stock_ret - bench_ret) * 100


def rvol_same_minute(today_cumulative_volume: float, comparable_cumulative_volumes, method: str = "median"):
    vols = pd.Series(comparable_cumulative_volumes, dtype="float64").dropna()
    if len(vols) < 10 or today_cumulative_volume is None:
        return {"rvol": None, "reliable": False, "method": method}
    base = vols.median() if method == "median" else vols.mean()
    if base <= 0:
        return {"rvol": None, "reliable": False, "method": method}
    return {"rvol": float(today_cumulative_volume / base), "reliable": True, "method": method}


def average_volume(df: pd.DataFrame, window: int = 20):
    return float(df["volume"].astype(float).tail(window).mean())


def average_dollar_volume(df: pd.DataFrame, window: int = 20):
    recent = df.tail(window)
    return float((recent["close"].astype(float) * recent["volume"].astype(float)).mean())


def distance_pct(value: float, reference: float):
    if reference == 0:
        return np.nan
    return ((value / reference) - 1) * 100
