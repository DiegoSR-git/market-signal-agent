from __future__ import annotations

from typing import Any

from .models import AlphaScore, CatalystSnapshot, MarketRegimeSnapshot, Regime, RiskCategory, ScoreComponent
from .risk import classify_risk


def clamp(value: float, maximum: float) -> float:
    return max(0.0, min(maximum, value))


def component(name: str, score: float, max_score: float, pos=None, neg=None, missing=None) -> ScoreComponent:
    return ScoreComponent(name, clamp(score, max_score), max_score, pos or [], neg or [], missing or [])


def score_daily(metrics: dict[str, Any]) -> ScoreComponent:
    score = 0
    pos: list[str] = []
    neg: list[str] = []
    missing: list[str] = []
    price, ema20, sma50, sma200 = (metrics.get(k) for k in ("price", "ema20", "sma50", "sma200"))
    if None in [price, ema20, sma50, sma200]:
        missing.append("price/EMA20/SMA50/SMA200")
    elif price > ema20 > sma50 > sma200:
        score += 6; pos.append("alineacion diaria alcista")
    else:
        neg.append("alineacion diaria incompleta")
    rsi_daily = metrics.get("rsi_daily")
    if rsi_daily is None:
        missing.append("RSI diario")
    elif 50 <= rsi_daily <= 70:
        score += 3; pos.append("RSI diario sano")
    elif rsi_daily > 78:
        neg.append("RSI diario extendido")
    macd_hist = metrics.get("macd_daily_hist")
    if macd_hist is None:
        missing.append("MACD diario")
    elif macd_hist > 0:
        score += 3; pos.append("MACD diario positivo")
    rs = metrics.get("relative_strength_daily")
    if rs is None:
        missing.append("fortaleza relativa diaria")
    elif rs > 0:
        score += 4; pos.append("fortaleza relativa diaria positiva")
    resistance_room = metrics.get("distance_to_resistance_pct")
    if resistance_room is None:
        missing.append("distancia a resistencia")
    elif resistance_room >= 1.5:
        score += 4; pos.append("espacio a resistencia")
    return component("daily_technical", score, 20, pos, neg, missing)


def score_intraday(metrics: dict[str, Any]) -> ScoreComponent:
    score = 0
    pos: list[str] = []
    neg: list[str] = []
    missing: list[str] = []
    if metrics.get("price_above_vwap") and metrics.get("vwap_slope") == "rising":
        score += 6; pos.append("precio sobre VWAP ascendente")
    else:
        neg.append("VWAP no confirma")
    if metrics.get("ema9_5m") is not None and metrics.get("ema20_5m") is not None and metrics["ema9_5m"] > metrics["ema20_5m"]:
        score += 4; pos.append("EMA9 5m > EMA20 5m")
    else:
        missing.append("EMA 5m") if metrics.get("ema9_5m") is None else neg.append("EMA 5m sin alineacion")
    rsi5 = metrics.get("rsi5")
    if rsi5 is None:
        missing.append("RSI5")
    elif 55 <= rsi5 <= 72:
        score += 4; pos.append("RSI5 operativo")
    elif rsi5 > 78:
        neg.append("RSI5 persecucion")
    if metrics.get("macd5_hist") is not None and metrics["macd5_hist"] > 0:
        score += 3; pos.append("MACD5 positivo")
    else:
        missing.append("MACD5")
    if metrics.get("hh_hl"):
        score += 4; pos.append("estructura HH/HL")
    if (metrics.get("relative_strength_spy") or 0) > 0 and (metrics.get("relative_strength_qqq") or 0) > 0:
        score += 3; pos.append("fuerza relativa vs SPY/QQQ")
    setup = metrics.get("setup_valid")
    if setup:
        score += 4; pos.append("setup tecnico validado")
    if (metrics.get("distance_to_resistance_pct") or 0) >= 1.5:
        score += 2; pos.append("recorrido suficiente")
    return component("intraday_technical", score, 30, pos, neg, missing)


def score_volume_liquidity(metrics: dict[str, Any], config: dict[str, Any]) -> ScoreComponent:
    score = 0
    pos: list[str] = []
    missing: list[str] = []
    uni = config.get("universe", {})
    if (metrics.get("average_volume") or 0) >= uni.get("min_average_volume", 1_000_000):
        score += 3; pos.append("ADV suficiente")
    else:
        missing.append("ADV")
    if (metrics.get("average_dollar_volume") or 0) >= uni.get("min_average_dollar_volume", 100_000_000):
        score += 3; pos.append("dollar ADV suficiente")
    else:
        missing.append("dollar ADV")
    spread_pct = metrics.get("spread_pct")
    if spread_pct is not None and spread_pct <= config.get("spread", {}).get("hard_max_spread_pct", 0.15):
        score += 3; pos.append("spread apto")
    else:
        missing.append("spread")
    if metrics.get("rvol_reliable") and (metrics.get("rvol") or 0) >= config.get("setups", {}).get("min_rvol", 1.5):
        score += 4; pos.append("RVOL fiable")
    else:
        missing.append("RVOL fiable")
    if (metrics.get("market_cap") or 0) >= uni.get("min_market_cap_usd", 10_000_000_000):
        score += 2; pos.append("market cap/liquidez calidad")
    return component("volume_liquidity", score, 15, pos, [], missing)


def score_analysts(analysts: dict[str, Any] | None, price: float | None, config: dict[str, Any]) -> ScoreComponent:
    if not analysts:
        return component("analysts", 0, 15, missing=["analistas"])
    score = 0
    pos: list[str] = []
    neg: list[str] = []
    missing: list[str] = []
    count = analysts.get("analyst_count")
    if count and count >= config.get("universe", {}).get("min_analysts", 8):
        score += 2; pos.append("cobertura de analistas suficiente")
    else:
        missing.append("analyst_count")
    target_median = analysts.get("target_median")
    if target_median and price:
        upside = ((target_median / price) - 1) * 100
        if upside > 20:
            score += 5; pos.append("upside mediano >20%")
        elif upside > 15:
            score += 4; pos.append("upside mediano >15%")
        else:
            neg.append("upside mediano limitado")
    else:
        missing.append("target_median")
    buys = (analysts.get("strong_buy") or 0) + (analysts.get("buy") or 0)
    total = count or 0
    sell_ratio = ((analysts.get("sell") or 0) + (analysts.get("strong_sell") or 0)) / total * 100 if total else None
    if total and buys / total >= 0.70:
        score += 4; pos.append("Buy + Strong Buy >=70%")
    if sell_ratio is not None and sell_ratio < 10:
        score += 2; pos.append("Sell ratio <10%")
    if analysts.get("recent_upgrades", 0) > analysts.get("recent_downgrades", 0):
        score += 2; pos.append("revisiones netas positivas")
    return component("analysts", score, 15, pos, neg, missing)


def score_catalyst(catalyst: CatalystSnapshot | None) -> ScoreComponent:
    if catalyst is None:
        return component("catalyst", 0, 10, missing=["catalizador"])
    cls = catalyst.classification
    if cls == "VERY_POSITIVE" and catalyst.confirmed_by_price_volume:
        return component("catalyst", 10, 10, ["catalizador muy positivo confirmado"])
    if cls == "POSITIVE" and catalyst.confirmed_by_price_volume:
        return component("catalyst", 7, 10, ["catalizador positivo confirmado"])
    if cls in {"NEUTRAL", "UNVERIFIED"}:
        return component("catalyst", 3 if cls == "NEUTRAL" else 0, 10, [], ["catalizador limitado o no verificado"])
    return component("catalyst", 0, 10, [], ["catalizador inexistente o negativo"])


def score_market_sector(regime: MarketRegimeSnapshot, metrics: dict[str, Any]) -> ScoreComponent:
    score = 0
    pos: list[str] = []
    neg: list[str] = []
    if regime.regime in {Regime.BULLISH, Regime.WEAK_BULLISH}:
        score += 4; pos.append("regimen favorable")
    elif regime.regime in {Regime.BEARISH, Regime.HIGH_VOLATILITY, Regime.BINARY_EVENT}:
        neg.append("regimen penaliza largos")
    if (metrics.get("spy_change_pct") or 0) > 0 and (metrics.get("qqq_change_pct") or 0) > 0:
        score += 3; pos.append("SPY/QQQ proxy positivos")
    if (metrics.get("sector_relative_strength") or 0) > 0:
        score += 2; pos.append("sector fuerte")
    if not metrics.get("binary_event_risk"):
        score += 1; pos.append("sin evento binario detectado")
    return component("market_sector", score, 10, pos, neg, [])


def build_score(metrics: dict[str, Any], analysts: dict[str, Any] | None, catalyst: CatalystSnapshot | None, regime: MarketRegimeSnapshot, config: dict[str, Any]) -> AlphaScore:
    comps = [
        score_daily(metrics),
        score_intraday(metrics),
        score_volume_liquidity(metrics, config),
        score_analysts(analysts, metrics.get("price"), config),
        score_catalyst(catalyst),
        score_market_sector(regime, metrics),
    ]
    total = min(100.0, sum(c.score for c in comps))
    risk = classify_risk(total, metrics, config)
    blocking = []
    if total < config.get("scoring", {}).get("minimum_general", 78):
        blocking.append("score < 78")
    if risk == RiskCategory.NONE:
        blocking.append("sin categoria de riesgo operable")
    return AlphaScore(round(total, 2), comps, risk, not blocking, blocking)
