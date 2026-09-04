from __future__ import annotations

import pandas as pd

from .data_quality import evaluate_alpha_quality, evaluate_bars_quality, spread_metrics
from .indicators import ema, macd, opening_range, regular_session_df, regular_session_vwap, resample_ohlcv, rsi
from .market_clock import classify_market_time
from .market_regime import classify_regime
from .config import live_signal_allowed
from .models import AlphaCandidate, AlphaMode, AlphaSnapshot, MarketStatus
from .readiness import ProviderBundle, build_readiness_report, provider_health
from .risk import build_risk_plan
from .scoring import build_score
from .setups import evaluate_setup
from .universe import eligible_universe


def bars_to_df(bars):
    if not bars:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    return pd.DataFrame([b.__dict__ for b in bars]).set_index("timestamp").sort_index()


def closed_resample(df: pd.DataFrame, rule: str, now) -> pd.DataFrame:
    if df.empty:
        return df
    resampled = resample_ohlcv(df, rule)
    duration = pd.Timedelta(rule)
    return resampled[resampled.index + duration <= now.astimezone(resampled.index.tz)]


def safe_last(series):
    return float(series.iloc[-1]) if series is not None and len(series) else None


def metrics_from_bars(symbol: str, quote, bars, meta, macro: dict, config: dict, now, supplied_metrics: dict | None = None) -> dict:
    df_all = bars_to_df([bar for bar in bars if bar.timestamp <= now])
    df_1m = regular_session_df(df_all, now=now)
    df_5m = closed_resample(df_1m, "5min", now)
    df_15m = closed_resample(df_1m, "15min", now)
    close_5m = df_5m["close"] if not df_5m.empty else pd.Series(dtype="float64")
    vw = regular_session_vwap(df_all, now=now)
    macd_line, macd_signal, macd_hist = macd(close_5m) if len(close_5m) else (pd.Series(dtype="float64"), pd.Series(dtype="float64"), pd.Series(dtype="float64"))
    or5 = opening_range(df_all, 5, now=now)
    or15 = opening_range(df_all, 15, now=now)
    spread = spread_metrics(quote.bid, quote.ask)
    quote_mid = spread["mid"]
    supplied = supplied_metrics or {}
    entry = supplied.get("entry")
    stop = supplied.get("stop")
    target1 = supplied.get("target1")
    target2 = supplied.get("target2")
    if quote_mid is not None and len(vw) and or5.get("high") is not None:
        entry = entry or round(max(quote_mid, or5["high"]) * 1.001, 2)
        stop = stop or round(min(float(vw.iloc[-1]) * 0.995, entry * 0.99), 2)
        target1 = target1 or round(entry + (entry - stop) * 1.6, 2)
        target2 = target2 or round(entry + (entry - stop) * 2.2, 2)
    bars_1m_quality = evaluate_bars_quality(df_all, now, "1m", 10, config.get("data", {}).get("bar_fresh_seconds", 120))
    bars_5m_quality = evaluate_bars_quality(df_5m, now, "5m", 2, 600)
    bars_15m_quality = evaluate_bars_quality(df_15m, now, "15m", 1, 1200)
    metrics = {
        "symbol": symbol,
        "latest_trade": None,
        "latest_trade_available": False,
        "quote_mid": quote_mid,
        "price": quote_mid,
        "bid": quote.bid,
        "ask": quote.ask,
        "spread_pct": spread["spread_pct"],
        "vwap": safe_last(vw),
        "vwap_slope": "rising" if len(vw) >= 3 and vw.iloc[-1] > vw.iloc[-3] else None,
        "price_above_vwap": quote_mid is not None and len(vw) and quote_mid > vw.iloc[-1],
        "ema9_5m": safe_last(ema(close_5m, 9)) if len(close_5m) else None,
        "ema20_5m": safe_last(ema(close_5m, 20)) if len(close_5m) else None,
        "rsi5": safe_last(rsi(close_5m, 5)) if len(close_5m) else None,
        "macd5_hist": safe_last(macd_hist),
        "hh_hl": bool(df_5m["high"].iloc[-1] > df_5m["high"].iloc[-2] and df_5m["low"].iloc[-1] > df_5m["low"].iloc[-2]) if len(df_5m) >= 2 else None,
        "relative_strength_spy": supplied.get("relative_strength_spy"),
        "relative_strength_qqq": supplied.get("relative_strength_qqq"),
        "relative_strength_daily": supplied.get("relative_strength_daily"),
        "sector_relative_strength": supplied.get("sector_relative_strength"),
        "rvol": supplied.get("rvol"),
        "rvol_reliable": supplied.get("rvol_reliable", False),
        "average_volume": meta.average_volume,
        "average_dollar_volume": meta.average_dollar_volume,
        "market_cap": meta.market_cap,
        "daily_history_available": supplied.get("daily_history_available", False),
        "bars_1m_available": bars_1m_quality["ok"],
        "bars_5m_available": bars_5m_quality["ok"],
        "bars_15m_available": bars_15m_quality["ok"],
        "bars_1m_quality": bars_1m_quality,
        "bars_5m_quality": bars_5m_quality,
        "bars_15m_quality": bars_15m_quality,
        "ema20": supplied.get("ema20"),
        "sma50": supplied.get("sma50"),
        "sma200": supplied.get("sma200"),
        "rsi_daily": supplied.get("rsi_daily"),
        "macd_daily_hist": supplied.get("macd_daily_hist"),
        "distance_to_resistance_pct": supplied.get("distance_to_resistance_pct"),
        "distance_from_vwap_pct": ((quote_mid / vw.iloc[-1]) - 1) * 100 if quote_mid is not None and len(vw) else None,
        "atr_consumed_pct": supplied.get("atr_consumed_pct"),
        "setup_valid": False,
        "breakout_valid": quote_mid is not None and or5["complete"] and or5["high"] is not None and quote_mid > or5["high"],
        "vwap_reclaim_valid": supplied.get("vwap_reclaim_valid", False),
        "controlled_pullback_valid": supplied.get("controlled_pullback_valid", False),
        "trigger": f"superar OR5/premarket con volumen en {symbol}",
        "entry": entry,
        "entry_zone": f"{entry:.2f} USD +/- buffer configurado" if entry else "pendiente",
        "stop": stop,
        "target1": target1,
        "target2": target2,
        "activation_conditions": ["spread valido", "volumen confirma", "precio mantiene VWAP", "no perseguir vela vertical"],
        "invalidation": f"perder {stop:.2f} USD o VWAP con volumen" if stop else "pendiente de stop tecnico",
        "spy_change_pct": macro.get("spy_change_pct"),
        "qqq_change_pct": macro.get("qqq_change_pct"),
        "binary_event_risk": supplied.get("binary_event_risk"),
        "or5": or5,
        "or15": or15,
    }
    metrics["setup_valid"] = bool(metrics["breakout_valid"] or metrics["vwap_reclaim_valid"] or metrics["controlled_pullback_valid"])
    return metrics


def build_snapshot(providers: dict | ProviderBundle, config: dict, now=None) -> AlphaSnapshot:
    bundle = providers if isinstance(providers, ProviderBundle) else ProviderBundle(**providers)
    providers = bundle.as_dict()
    clock = classify_market_time(now)
    macro = providers["macro"].snapshot()
    regime = classify_regime(macro)
    market = providers["market_data"]
    universe = providers["universe"].list_metadata()
    quotes = {meta.symbol: market.latest_quote(meta.symbol) for meta in universe}
    prices = {sym: spread_metrics(q.bid, q.ask)["mid"] for sym, q in quotes.items()}
    accepted, rejected = eligible_universe(universe, providers["analysts"], prices, config)
    candidates: list[AlphaCandidate] = []
    for meta, analysts in accepted[:25]:
        quote = quotes[meta.symbol]
        bars = market.intraday_bars(meta.symbol, limit=180)
        catalyst = providers["news"].latest_catalyst(meta.symbol)
        supplied = market.synthetic_metrics(meta.symbol) if hasattr(market, "synthetic_metrics") else {}
        metrics = metrics_from_bars(meta.symbol, quote, bars, meta, macro, config, clock.now_et, supplied)
        quality = evaluate_alpha_quality(
            market_status=clock.status,
            quote=quote,
            now=clock.now_et,
            metrics=metrics,
            analysts_count=analysts.analyst_count if analysts else None,
            config=config,
        )
        score = build_score(metrics, analysts.__dict__ if analysts else None, catalyst, regime, config)
        setup = evaluate_setup(metrics, clock.status, clock.now_et, config)
        risk_category = score.risk_category
        eurusd, _fx_source = providers["fx"].eurusd()
        risk = build_risk_plan(entry=metrics.get("entry"), stop=metrics.get("stop"), risk_category=risk_category, eurusd=eurusd, config=config)
        if not quality["ok"]:
            score = score.__class__(score.total, score.components, score.risk_category, False, score.blocking_reasons + quality["blocking_reasons"])
        candidates.append(AlphaCandidate(meta.symbol, meta.company, metrics.get("price"), quote, meta, analysts, catalyst, metrics, quality, score, setup, risk))
    valid = [c for c in candidates if c.score.candidate_valid and c.setup.status.value == "READY_LONG" and c.risk and c.risk.position_size_available]
    best = sorted(valid, key=lambda c: (c.score.total, c.setup.risk_reward1 or 0, -(c.metrics.get("spread_pct") or 99)), reverse=True)[:1]
    blocking = []
    sample = {
        "quote_available": bool(quotes) and all(q.bid is not None and q.ask is not None for q in quotes.values()),
        "bars_available": bool(candidates) and any(c.metrics.get("bars_1m_available") for c in candidates),
        "freshness_ok": bool(candidates) and all(c.data_quality.get("quote_quality", {}).get("ok") for c in candidates),
    }
    readiness = build_readiness_report(bundle, config, all(c.data_quality.get("ok") for c in candidates) if candidates else False, sample)
    if config.get("mode") == AlphaMode.DEVELOPMENT.value:
        blocking.append("DEVELOPMENT MODE: live_signal_allowed=false")
    elif not config.get("live_signals"):
        blocking.append("ALPHA_LIVE_SIGNALS=false")
    if not readiness.production_ready:
        blocking.append("PRODUCTION_READY=false")
        blocking.extend(readiness.blocking_reasons()[:4])
    if clock.status != MarketStatus.SELECTION_WINDOW:
        blocking.append(clock.reason)
    if rejected:
        blocking.append(f"{len(rejected)} simbolos rechazados por filtros duros")
    return AlphaSnapshot(
        analysis_timestamp=clock.now_et,
        timezone="America/New_York",
        market_status=clock.status,
        data_mode=AlphaMode(config.get("mode", "development")),
        data_feed=config.get("data", {}).get("alpaca_feed", "iex"),
        provider_health=provider_health(bundle),
        production_readiness=readiness,
        market_regime=regime,
        candidates=candidates,
        best_operation=None if blocking else (best[0] if best else None),
        signal_allowed=live_signal_allowed(config, not blocking and bool(best), readiness.production_ready),
        blocking_reasons=blocking or (["NO OPERAR: ninguna candidata valida"] if not best else []),
    )
