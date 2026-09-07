from __future__ import annotations

from .models import MarketRegimeSnapshot, Regime


def classify_regime(macro: dict) -> MarketRegimeSnapshot:
    spy = macro.get("spy_change_pct")
    qqq = macro.get("qqq_change_pct")
    vix = macro.get("vix")
    reasons: list[str] = []
    if vix is not None and vix >= 25:
        return MarketRegimeSnapshot(Regime.HIGH_VOLATILITY, spy, qqq, vix, macro.get("us10y"), False, ["VIX alto"])
    if spy is None or qqq is None:
        return MarketRegimeSnapshot(Regime.NEUTRAL, spy, qqq, vix, macro.get("us10y"), False, ["SPY/QQQ no verificados"])
    if spy > 0.4 and qqq > 0.4:
        regime = Regime.BULLISH
        reasons.append("SPY y QQQ positivos")
    elif spy > 0 and qqq > 0:
        regime = Regime.WEAK_BULLISH
        reasons.append("SPY y QQQ ligeramente positivos")
    elif spy < -0.5 and qqq < -0.5:
        regime = Regime.BEARISH
        reasons.append("SPY y QQQ bajistas")
    elif spy < 0 or qqq < 0:
        regime = Regime.WEAK_BEARISH
        reasons.append("debilidad parcial en SPY/QQQ")
    else:
        regime = Regime.NEUTRAL
        reasons.append("regimen mixto")
    return MarketRegimeSnapshot(regime, spy, qqq, vix, macro.get("us10y"), False, reasons)
