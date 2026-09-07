from __future__ import annotations

import math
from typing import Any

from .models import RiskCategory, RiskPlan


def classify_risk(score: float, metrics: dict[str, Any], config: dict[str, Any]) -> RiskCategory:
    cfg = config.get("scoring", {})
    market_cap = float(metrics.get("market_cap") or 0)
    spread_pct = float(metrics.get("spread_pct") or 999)
    if score >= float(cfg.get("low_risk_min", 85)) and market_cap >= 100_000_000_000 and spread_pct <= 0.05:
        return RiskCategory.LOW
    if score >= float(cfg.get("medium_risk_min", 82)) and market_cap >= 30_000_000_000 and spread_pct <= 0.10:
        return RiskCategory.MEDIUM
    if score >= float(cfg.get("high_risk_min", 78)) and market_cap >= 10_000_000_000 and spread_pct <= 0.15:
        return RiskCategory.HIGH
    return RiskCategory.NONE


def risk_reward(entry: float | None, stop: float | None, target: float | None) -> float | None:
    if entry is None or stop is None or target is None:
        return None
    risk = entry - stop
    reward = target - entry
    if risk <= 0 or reward <= 0:
        return None
    return reward / risk


def build_risk_plan(
    *,
    entry: float | None,
    stop: float | None,
    risk_category: RiskCategory,
    eurusd: float | None,
    config: dict[str, Any],
) -> RiskPlan:
    risk_cfg = config.get("risk", {})
    account_value = float(risk_cfg.get("account_value", 5000))
    max_daily_risk = account_value * float(risk_cfg.get("max_daily_risk_pct", 1.0)) / 100
    pct = float(risk_cfg.get("risk_pct", {}).get(risk_category.value, 0))
    risk_eur = min(account_value * pct / 100, max_daily_risk)
    blocking: list[str] = []
    if risk_category == RiskCategory.NONE:
        blocking.append("sin categoria de riesgo operable")
    if float(risk_cfg.get("leverage", 1)) != 1:
        blocking.append("apalancamiento prohibido")
    if entry is None or stop is None or stop >= entry:
        blocking.append("stop invalido para LONG")
    if eurusd is None or eurusd <= 0:
        blocking.append("EUR/USD no verificado")
    if blocking:
        return RiskPlan("EUR", risk_category, risk_eur, None, None, None, max_daily_risk, False, blocking)
    risk_usd = risk_eur * eurusd
    per_share_risk = entry - stop
    shares = math.floor(risk_usd / per_share_risk)
    notional = shares * entry
    max_notional = account_value * eurusd
    if shares <= 0:
        blocking.append("tamano inferior a 1 accion")
    if notional > max_notional:
        shares = math.floor(max_notional / entry)
        notional = shares * entry
    if shares <= 0:
        blocking.append("notional excede cuenta sin apalancamiento")
    return RiskPlan("EUR", risk_category, risk_eur, risk_usd, shares, notional, max_daily_risk, not blocking, blocking)
