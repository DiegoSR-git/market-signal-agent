from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

from .indicators import regular_session_df
from .models import MarketStatus, Quote


def age_seconds(source_timestamp: datetime | None, now: datetime) -> float | None:
    if source_timestamp is None:
        return None
    return max(0.0, (now - source_timestamp.astimezone(now.tzinfo)).total_seconds())


def spread_metrics(bid: float | None, ask: float | None) -> dict[str, float | None]:
    if bid is None or ask is None or bid <= 0 or ask <= 0 or ask < bid:
        return {"mid": None, "spread_abs": None, "spread_pct": None}
    mid = (bid + ask) / 2
    spread_abs = ask - bid
    return {"mid": mid, "spread_abs": spread_abs, "spread_pct": (spread_abs / mid) * 100}


def evaluate_quote_quality(quote: Quote | None, now: datetime, config: dict[str, Any]) -> dict[str, Any]:
    max_age = float(config.get("data", {}).get("quote_fresh_seconds", 5))
    hard_spread = float(config.get("spread", {}).get("hard_max_spread_pct", 0.15))
    blocking: list[str] = []
    warnings: list[str] = []
    if quote is None:
        return {"ok": False, "status": "DATA_BLOCKED", "blocking_reasons": ["quote ausente"], "warnings": []}
    if quote.bid is None:
        blocking.append("bid ausente")
    if quote.ask is None:
        blocking.append("ask ausente")
    spread = spread_metrics(quote.bid, quote.ask)
    if spread["spread_pct"] is None:
        blocking.append("spread no calculable")
    elif spread["spread_pct"] > hard_spread:
        blocking.append(f"spread demasiado alto: {spread['spread_pct']:.3f}%")
    age = age_seconds(quote.timestamp, now)
    if age is None:
        blocking.append("timestamp de quote ausente")
    elif age > max_age:
        blocking.append(f"quote stale: {age:.1f}s")
    elif age > max_age / 2:
        warnings.append(f"quote envejeciendo: {age:.1f}s")
    return {
        "ok": not blocking,
        "status": "OK" if not blocking else "DATA_BLOCKED",
        "age_seconds": age,
        "spread": spread,
        "blocking_reasons": blocking,
        "warnings": warnings,
        "provider": quote.provider,
        "feed": quote.feed,
    }


def evaluate_alpha_quality(
    *,
    market_status: MarketStatus,
    quote: Quote | None,
    now: datetime,
    metrics: dict[str, Any],
    analysts_count: int | None,
    config: dict[str, Any],
) -> dict[str, Any]:
    quote_quality = evaluate_quote_quality(quote, now, config)
    blocking = list(quote_quality.get("blocking_reasons", []))
    required_fields = [
        "quote_mid",
        "vwap",
        "rvol",
        "rvol_reliable",
        "daily_history_available",
        "bars_1m_available",
        "bars_5m_available",
        "bars_15m_available",
        "relative_strength_spy",
        "relative_strength_qqq",
    ]
    for field in required_fields:
        if metrics.get(field) in [None, "", False]:
            blocking.append(f"{field} no disponible o no fiable")
    min_analysts = int(config.get("universe", {}).get("min_analysts", 8))
    if analysts_count is None or analysts_count < min_analysts:
        blocking.append(f"analistas insuficientes: {analysts_count}")
    if market_status in {MarketStatus.CLOSED, MarketStatus.HOLIDAY, MarketStatus.AFTER_HOURS}:
        blocking.append(f"estado de mercado no valido: {market_status.value}")
    return {
        "ok": not blocking,
        "signal_allowed": not blocking,
        "quote_quality": quote_quality,
        "blocking_reasons": blocking,
        "standard_output": "OK" if not blocking else "NO OPERAR - datos insuficientemente actuales o inconsistentes.",
    }


def evaluate_bars_quality(df: pd.DataFrame, now: datetime, timeframe: str, min_bars: int, max_age_seconds: float, regular_session_only: bool = True) -> dict[str, Any]:
    blocking: list[str] = []
    if df is None or df.empty:
        return {
            "ok": False,
            "timeframe": timeframe,
            "last_bar_timestamp": None,
            "bar_age_seconds": None,
            "bars_count": 0,
            "bars_complete": False,
            "blocking_reasons": ["barras ausentes"],
        }
    working = regular_session_df(df, now=now) if regular_session_only else df
    if working.empty:
        blocking.append("sin barras de sesion regular")
        return {
            "ok": False,
            "timeframe": timeframe,
            "last_bar_timestamp": None,
            "bar_age_seconds": None,
            "bars_count": 0,
            "bars_complete": False,
            "blocking_reasons": blocking,
        }
    future = working[working.index > now.astimezone(working.index.tz)]
    if not future.empty:
        blocking.append("barras futuras detectadas")
    count = len(working)
    if count < min_bars:
        blocking.append(f"barras insuficientes {count}/{min_bars}")
    last_ts = working.index[-1] if count else None
    age = age_seconds(last_ts.to_pydatetime() if last_ts is not None else None, now)
    if age is None:
        blocking.append("timestamp ultima barra ausente")
    elif age > max_age_seconds:
        blocking.append(f"barras stale: {age:.1f}s")
    if count >= 2:
        deltas = working.index.to_series().diff().dropna().dt.total_seconds()
        expected = {"1m": 60, "5m": 300, "15m": 900}.get(timeframe)
        if expected and not deltas.tail(min(10, len(deltas))).between(expected * 0.8, expected * 1.5).all():
            blocking.append("continuidad de barras irregular")
    return {
        "ok": not blocking,
        "timeframe": timeframe,
        "last_bar_timestamp": last_ts.isoformat() if last_ts is not None else None,
        "bar_age_seconds": age,
        "bars_count": count,
        "bars_complete": not blocking,
        "blocking_reasons": blocking,
    }


def providers_consistent(values: dict[str, float | None], tolerance_pct: float = 0.15) -> dict[str, Any]:
    clean = {k: v for k, v in values.items() if v is not None}
    if len(clean) < 2:
        return {"consistent": True, "reason": "comparacion no aplicable"}
    vals = list(clean.values())
    midpoint = sum(vals) / len(vals)
    if midpoint == 0:
        return {"consistent": False, "reason": "midpoint cero"}
    max_deviation = max(abs(v - midpoint) / midpoint * 100 for v in vals)
    return {
        "consistent": max_deviation <= tolerance_pct,
        "max_deviation_pct": max_deviation,
        "reason": "OK" if max_deviation <= tolerance_pct else "DATA_BLOCKED por contradiccion entre proveedores",
    }
