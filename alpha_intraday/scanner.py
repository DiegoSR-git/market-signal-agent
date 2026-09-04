from __future__ import annotations

import pandas as pd

from .data_quality import evaluate_alpha_quality, evaluate_bars_quality, spread_metrics
from .indicators import ema, historical_regular_session_df, macd, opening_range, regular_session_df, regular_session_vwap, resample_ohlcv, rsi
from .market_clock import classify_market_time
from .market_regime import classify_regime
from .config import live_signal_allowed
from .models import AlphaCandidate, AlphaMode, AlphaSnapshot, MarketStatus
from .readiness import ProviderBundle, build_readiness_report, provider_health
from .risk import build_risk_plan
from .scoring import build_score
from .setups import evaluate_setup
from .universe import eligible_universe


class CachedAnalystProvider:
    def __init__(self, snapshots: dict):
        self.snapshots = snapshots

    def snapshot(self, symbol: str):
        return self.snapshots.get(symbol)


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


def metrics_from_bars(symbol: str, quote, bars, meta, macro: dict, config: dict, now, supplied_metrics: dict | None = None, indicator_history_bars=None) -> dict:
    df_all = bars_to_df([bar for bar in bars if bar.timestamp <= now])
    df_1m = regular_session_df(df_all, now=now)
    history_source = indicator_history_bars if indicator_history_bars is not None else bars
    df_history_all = bars_to_df([bar for bar in history_source if bar.timestamp <= now])
    df_history_regular = historical_regular_session_df(df_history_all, now=now)
    indicator_history_5m = closed_resample(df_history_regular, "5min", now)
    current_session_5m = closed_resample(df_1m, "5min", now)
    df_15m = closed_resample(df_1m, "15min", now)
    close_5m = indicator_history_5m["close"] if not indicator_history_5m.empty else pd.Series(dtype="float64")
    vw = regular_session_vwap(df_all, now=now)
    min_indicator_5m = int(config.get("data", {}).get("min_indicator_5m_bars", 20))
    min_current_5m = int(config.get("data", {}).get("min_current_5m_bars", 2))
    min_macd = int(config.get("data", {}).get("min_macd_5m_bars", 35))
    indicator_cfg = config.get("indicators", {})
    rsi_period = int(indicator_cfg.get("rsi_period", 14))
    macd_fast = int(indicator_cfg.get("macd_fast", 12))
    macd_slow = int(indicator_cfg.get("macd_slow", 26))
    macd_signal_period = int(indicator_cfg.get("macd_signal", 9))
    indicators_5m_available = len(close_5m) >= min_indicator_5m
    macd_available = len(close_5m) >= min_macd
    macd_line, macd_signal, macd_hist = macd(close_5m, macd_fast, macd_slow, macd_signal_period) if macd_available else (pd.Series(dtype="float64"), pd.Series(dtype="float64"), pd.Series(dtype="float64"))
    or5 = opening_range(df_all, 5, now=now)
    or15 = opening_range(df_all, 15, now=now)
    spread = spread_metrics(quote.bid, quote.ask)
    quote_mid = spread["mid"]
    supplied = supplied_metrics or {}
    entry = supplied.get("entry")
    stop = supplied.get("stop")
    target1 = supplied.get("target1")
    target2 = supplied.get("target2")
    bars_1m_quality = evaluate_bars_quality(df_all, now, "1m", config.get("data", {}).get("min_1m_bars", 10), config.get("data", {}).get("bar_fresh_seconds", 120))
    bars_5m_quality = evaluate_bars_quality(current_session_5m, now, "5m", min_current_5m, 1800)
    bars_15m_quality = evaluate_bars_quality(df_15m, now, "15m", config.get("data", {}).get("min_15m_bars", 1), 1800)
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
        "indicator_history_5m_bars": len(indicator_history_5m),
        "current_session_5m_bars": len(current_session_5m),
        "indicators_5m_available": indicators_5m_available,
        "macd_5m_available": macd_available,
        "ema9_5m": safe_last(ema(close_5m, 9)) if indicators_5m_available else None,
        "ema20_5m": safe_last(ema(close_5m, 20)) if indicators_5m_available else None,
        "rsi5": safe_last(rsi(close_5m, rsi_period)) if indicators_5m_available else None,
        "macd5_hist": safe_last(macd_hist) if macd_available else None,
        "hh_hl": bool(current_session_5m["high"].iloc[-1] > current_session_5m["high"].iloc[-2] and current_session_5m["low"].iloc[-1] > current_session_5m["low"].iloc[-2]) if len(current_session_5m) >= 2 else None,
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
        "entry_zone": supplied.get("entry_zone") or (f"{entry:.2f} USD +/- buffer configurado" if entry else "pendiente"),
        "stop": stop,
        "target1": target1,
        "target2": target2,
        "activation_conditions": ["spread valido", "volumen confirma", "precio mantiene VWAP", "no perseguir vela vertical"],
        "invalidation": supplied.get("invalidation") or (f"perder {stop:.2f} USD o VWAP con volumen" if stop else "pendiente de stop tecnico"),
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
    provider_errors: dict[str, list[str]] = {}

    def record_error(provider_name: str, message: str) -> None:
        provider_errors.setdefault(provider_name, []).append(message)

    try:
        macro = providers["macro"].snapshot()
    except Exception as ex:
        record_error("macro", str(ex))
        macro = {}
    try:
        index_snapshot = providers["index_data"].snapshot() if providers.get("index_data") else {}
    except Exception as ex:
        record_error("index_data", str(ex))
        index_snapshot = {}
    regime = classify_regime(macro)
    market = providers["market_data"]
    try:
        universe = providers["universe"].list_metadata()
    except Exception as ex:
        record_error("universe", str(ex))
        universe = []
    quotes = {}
    for meta in universe:
        try:
            quotes[meta.symbol] = market.latest_quote(meta.symbol)
        except Exception as ex:
            record_error("market_data", f"{meta.symbol} quote: {ex}")
    prices = {sym: spread_metrics(q.bid, q.ask)["mid"] for sym, q in quotes.items()}
    analyst_snapshots = {}
    for meta in universe:
        try:
            analyst_snapshots[meta.symbol] = providers["analysts"].snapshot(meta.symbol) if providers["analysts"] else None
        except Exception as ex:
            record_error("analysts", f"{meta.symbol}: {ex}")
            analyst_snapshots[meta.symbol] = None
    accepted, rejected = eligible_universe(universe, CachedAnalystProvider(analyst_snapshots), prices, config)
    for meta in universe:
        if meta.symbol not in quotes:
            rejected.setdefault(meta.symbol, []).append("quote no disponible por error de proveedor")
    candidates: list[AlphaCandidate] = []
    history_limit = max(500, int(config.get("data", {}).get("min_macd_5m_bars", 35)) * 5 + 180)
    for meta, analysts in accepted[:25]:
        quote = quotes[meta.symbol]
        try:
            bars = market.intraday_bars(meta.symbol, limit=180)
        except Exception as ex:
            record_error("market_data", f"{meta.symbol} bars: {ex}")
            rejected.setdefault(meta.symbol, []).append("barras no disponibles por error de proveedor")
            continue
        try:
            indicator_history = market.intraday_bars(meta.symbol, limit=history_limit)
        except Exception as ex:
            record_error("market_data", f"{meta.symbol} indicator_history: {ex}")
            indicator_history = bars
        try:
            catalyst = providers["news"].latest_catalyst(meta.symbol)
        except Exception as ex:
            record_error("news", f"{meta.symbol}: {ex}")
            catalyst = None
        supplied = market.synthetic_metrics(meta.symbol) if hasattr(market, "synthetic_metrics") else {}
        metrics = metrics_from_bars(meta.symbol, quote, bars, meta, macro, config, clock.now_et, supplied, indicator_history_bars=indicator_history)
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
        try:
            eurusd, _fx_source = providers["fx"].eurusd()
        except Exception as ex:
            record_error("fx", str(ex))
            eurusd = None
        risk = build_risk_plan(entry=metrics.get("entry"), stop=metrics.get("stop"), risk_category=risk_category, eurusd=eurusd, config=config)
        if not quality["ok"]:
            score = score.__class__(score.total, score.components, score.risk_category, False, score.blocking_reasons + quality["blocking_reasons"])
        candidates.append(AlphaCandidate(meta.symbol, meta.company, metrics.get("price"), quote, meta, analysts, catalyst, metrics, quality, score, setup, risk))
    valid = [c for c in candidates if c.score.candidate_valid and c.setup.status.value == "READY_LONG" and c.risk and c.risk.position_size_available]
    best = sorted(valid, key=lambda c: (c.score.total, c.setup.risk_reward1 or 0, -(c.metrics.get("spread_pct") or 99)), reverse=True)[:1]
    blocking = []
    sample = {
        "quote_available": bool(quotes) and all(q.bid is not None and q.ask is not None for q in quotes.values()),
        "latest_trade_available": bool(candidates) and all(c.metrics.get("latest_trade_available") for c in candidates),
        "bars_available": bool(candidates) and any(c.metrics.get("bars_1m_available") for c in candidates),
        "freshness_ok": bool(candidates) and all(c.data_quality.get("quote_quality", {}).get("ok") for c in candidates),
        "index_data_verified": bool(index_snapshot.get("actual_index_verified")),
    }
    readiness = build_readiness_report(bundle, config, all(c.data_quality.get("ok") for c in candidates) if candidates else False, sample, provider_errors)
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
    for provider_name, errors in provider_errors.items():
        blocking.append(f"{provider_name} BLOCKED: {errors[0]}")
    return AlphaSnapshot(
        analysis_timestamp=clock.now_et,
        timezone="America/New_York",
        market_status=clock.status,
        data_mode=AlphaMode(config.get("mode", "development")),
        data_feed=config.get("data", {}).get("alpaca_feed", "iex"),
        provider_health=provider_health(bundle, provider_errors),
        production_readiness=readiness,
        market_regime=regime,
        candidates=candidates,
        best_operation=None if blocking else (best[0] if best else None),
        signal_allowed=live_signal_allowed(config, not blocking and bool(best), readiness.production_ready),
        blocking_reasons=blocking or (["NO OPERAR: ninguna candidata valida"] if not best else []),
    )
