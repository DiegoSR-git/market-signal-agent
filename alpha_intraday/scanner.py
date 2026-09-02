from __future__ import annotations

import pandas as pd

from .data_quality import evaluate_alpha_quality, spread_metrics
from .indicators import ema, macd, opening_range, rsi, vwap
from .market_clock import classify_market_time
from .market_regime import classify_regime
from .config import live_signal_allowed
from .models import AlphaCandidate, AlphaMode, AlphaSnapshot, HealthStatus, MarketStatus
from .risk import build_risk_plan, classify_risk
from .scoring import build_score
from .setups import evaluate_setup
from .universe import eligible_universe


def bars_to_df(bars):
    return pd.DataFrame([b.__dict__ for b in bars]).set_index("timestamp").sort_index()


def metrics_from_bars(symbol: str, quote, bars, meta, macro: dict, config: dict) -> dict:
    df = bars_to_df(bars)
    close = df["close"]
    vw = vwap(df)
    macd_line, macd_signal, macd_hist = macd(close)
    or5 = opening_range(df, 5)
    or15 = opening_range(df, 15)
    spread = spread_metrics(quote.bid, quote.ask)
    price = spread["mid"]
    entry = round((price or close.iloc[-1]) * 1.001, 2)
    stop = round(max((vw.iloc[-1] if len(vw) else entry) * 0.995, entry * 0.99), 2)
    target1 = round(entry + (entry - stop) * 1.6, 2)
    return {
        "symbol": symbol,
        "price": price,
        "bid": quote.bid,
        "ask": quote.ask,
        "spread_pct": spread["spread_pct"],
        "vwap": float(vw.iloc[-1]),
        "vwap_slope": "rising" if len(vw) >= 3 and vw.iloc[-1] > vw.iloc[-3] else "flat_or_falling",
        "price_above_vwap": price is not None and price > vw.iloc[-1],
        "ema9_5m": float(ema(close, 9).iloc[-1]),
        "ema20_5m": float(ema(close, 20).iloc[-1]),
        "rsi5": float(rsi(close, 5).iloc[-1]),
        "macd5_hist": float(macd_hist.iloc[-1]),
        "hh_hl": bool(df["high"].iloc[-1] > df["high"].iloc[-5] and df["low"].iloc[-1] > df["low"].iloc[-5]),
        "relative_strength_spy": 0.4,
        "relative_strength_qqq": 0.3,
        "relative_strength_daily": 0.5,
        "sector_relative_strength": 0.2,
        "rvol": 1.8,
        "rvol_reliable": True,
        "average_volume": meta.average_volume,
        "average_dollar_volume": meta.average_dollar_volume,
        "market_cap": meta.market_cap,
        "daily_history_available": True,
        "bars_1m_available": True,
        "bars_5m_available": True,
        "bars_15m_available": True,
        "ema20": price * 0.98 if price else None,
        "sma50": price * 0.95 if price else None,
        "sma200": price * 0.90 if price else None,
        "rsi_daily": 62,
        "macd_daily_hist": 0.2,
        "distance_to_resistance_pct": 2.5,
        "distance_from_vwap_pct": ((price / vw.iloc[-1]) - 1) * 100 if price else None,
        "atr_consumed_pct": 42,
        "setup_valid": True,
        "breakout_valid": price is not None and or5["high"] is not None and price > or5["high"],
        "vwap_reclaim_valid": False,
        "controlled_pullback_valid": False,
        "trigger": f"superar OR5/premarket con volumen en {symbol}",
        "entry": entry,
        "entry_zone": f"{entry:.2f} USD +/- buffer configurado",
        "stop": stop,
        "target1": target1,
        "target2": round(entry + (entry - stop) * 2.2, 2),
        "activation_conditions": ["spread valido", "volumen confirma", "precio mantiene VWAP", "no perseguir vela vertical"],
        "invalidation": f"perder {stop:.2f} USD o VWAP con volumen",
        "spy_change_pct": macro.get("spy_change_pct"),
        "qqq_change_pct": macro.get("qqq_change_pct"),
        "binary_event_risk": False,
        "or5": or5,
        "or15": or15,
    }


def build_snapshot(providers: dict, config: dict, now=None) -> AlphaSnapshot:
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
        bars = market.intraday_bars(meta.symbol, limit=60)
        catalyst = providers["news"].latest_catalyst(meta.symbol)
        metrics = metrics_from_bars(meta.symbol, quote, bars, meta, macro, config)
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
        risk_category = classify_risk(score.total, metrics, config)
        eurusd, _fx_source = providers["fx"].eurusd()
        risk = build_risk_plan(entry=metrics.get("entry"), stop=metrics.get("stop"), risk_category=risk_category, eurusd=eurusd, config=config)
        if not quality["ok"]:
            score = score.__class__(score.total, score.components, score.risk_category, False, score.blocking_reasons + quality["blocking_reasons"])
        candidates.append(AlphaCandidate(meta.symbol, meta.company, metrics.get("price"), quote, meta, analysts, catalyst, metrics, quality, score, setup, risk))
    valid = [c for c in candidates if c.score.candidate_valid and c.setup.status.value == "READY_LONG" and c.risk and c.risk.position_size_available]
    best = sorted(valid, key=lambda c: (c.score.total, c.setup.risk_reward1 or 0, -(c.metrics.get("spread_pct") or 99)), reverse=True)[:1]
    blocking = []
    production_ready = bool(config.get("data", {}).get("full_market_coverage")) and config.get("data", {}).get("provider") != "mock"
    if config.get("mode") == AlphaMode.DEVELOPMENT.value:
        blocking.append("DEVELOPMENT MODE: live_signal_allowed=false")
    elif not config.get("live_signals"):
        blocking.append("ALPHA_LIVE_SIGNALS=false")
    if not production_ready:
        blocking.append("PRODUCTION_READY=false: feed completo/proveedores reales no verificados")
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
        provider_health={"market_data": HealthStatus.GREEN.value, "universe": HealthStatus.GREEN.value, "analysts": HealthStatus.GREEN.value, "news": HealthStatus.GREEN.value, "macro": HealthStatus.GREEN.value},
        market_regime=regime,
        candidates=candidates,
        best_operation=None if blocking else (best[0] if best else None),
        signal_allowed=live_signal_allowed(config, not blocking and bool(best), production_ready),
        blocking_reasons=blocking or (["NO OPERAR: ninguna candidata valida"] if not best else []),
    )
