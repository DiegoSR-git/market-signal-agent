from __future__ import annotations

from datetime import datetime
from typing import Any

from .market_clock import next_regular_open
from .models import MarketStatus, SetupPlan, SetupType, SignalStatus
from .risk import risk_reward


def chase_blocked(metrics: dict[str, Any], config: dict[str, Any]) -> list[str]:
    cfg = config.get("setups", {})
    blocks: list[str] = []
    if (metrics.get("rsi5") or 0) > cfg.get("max_rsi5", 78):
        blocks.append("RSI5 demasiado extendido")
    if abs(metrics.get("distance_from_vwap_pct") or 0) > cfg.get("max_distance_vwap_pct", 1.2):
        blocks.append("precio demasiado lejos de VWAP")
    if (metrics.get("atr_consumed_pct") or 0) > cfg.get("max_atr_consumed_pct", 75):
        blocks.append("ATR intradia demasiado consumido")
    if (metrics.get("vertical_move_pct_5m") or 0) > cfg.get("vertical_move_max_pct_5m", 2.5):
        blocks.append("movimiento vertical sin consolidacion")
    return blocks


def common_plan(setup_type, status, metrics, reason, config) -> SetupPlan:
    entry = metrics.get("entry")
    stop = metrics.get("stop")
    target1 = metrics.get("target1")
    target2 = metrics.get("target2")
    return SetupPlan(
        setup_type=setup_type,
        status=status,
        trigger=metrics.get("trigger", "condicion no confirmada"),
        entry_zone=metrics.get("entry_zone", "pendiente"),
        activation_conditions=metrics.get("activation_conditions", []),
        invalidation=metrics.get("invalidation", "perdida de nivel tecnico"),
        stop=stop,
        target1=target1,
        target2=target2,
        risk_reward1=risk_reward(entry, stop, target1),
        risk_reward2=risk_reward(entry, stop, target2),
        expires_at=metrics.get("expires_at"),
        evidence=[reason],
    )


def evaluate_setup(metrics: dict[str, Any], market_status: MarketStatus, now: datetime, config: dict[str, Any]) -> SetupPlan:
    if market_status == MarketStatus.PREMARKET:
        return SetupPlan(SetupType.NO_SETUP, SignalStatus.PRESELECTED, "esperar apertura", "pendiente", ["confirmar tras 09:40 ET"], "sin confirmacion regular", None, None, None, None, None, next_regular_open(now), ["premarket no puede READY_LONG"])
    if market_status != MarketStatus.SELECTION_WINDOW:
        return SetupPlan(SetupType.NO_SETUP, SignalStatus.WAIT, "fuera de ventana", "pendiente", [], "fuera de ventana 09:40-10:15 ET", None, None, None, None, None, None, ["new_entry_allowed=false"])
    blocks = chase_blocked(metrics, config)
    if blocks:
        return SetupPlan(SetupType.NO_SETUP, SignalStatus.NO_TRADE, "bloqueado por extension", "sin entrada", [], "; ".join(blocks), None, None, None, None, None, None, blocks)
    min_rr = float(config.get("risk", {}).get("min_risk_reward", 1.5))
    for setup in (SetupType.BREAKOUT, SetupType.VWAP_RECLAIM, SetupType.CONTROLLED_PULLBACK):
        if metrics.get(f"{setup.value.lower()}_valid"):
            plan = common_plan(setup, SignalStatus.READY_LONG, metrics, f"{setup.value} confirmado", config)
            if (plan.risk_reward1 or 0) < min_rr:
                return SetupPlan(setup, SignalStatus.NO_TRADE, plan.trigger, plan.entry_zone, plan.activation_conditions, "B/R < 1.5", plan.stop, plan.target1, plan.target2, plan.risk_reward1, plan.risk_reward2, plan.expires_at, ["B/R insuficiente"])
            return plan
    return SetupPlan(SetupType.NO_SETUP, SignalStatus.WAIT, "esperar condicion", "pendiente", ["breakout, VWAP reclaim o pullback controlado"], "setup no confirmado", None, None, None, None, None, None, ["score alto no activa entrada sin setup"])
