from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from .models import AlphaMode


DEFAULT_CONFIG: dict[str, Any] = {
    "mode": "development",
    "live_signals": False,
    "data": {
        "provider": "mock",
        "alpaca_feed": "iex",
        "full_market_coverage": False,
        "quote_fresh_seconds": 5,
        "trade_fresh_seconds": 300,
        "bar_fresh_seconds": 120,
        "min_1m_bars": 10,
        "min_indicator_5m_bars": 20,
        "min_current_5m_bars": 2,
        "min_15m_bars": 1,
        "min_macd_5m_bars": 35,
    },
    "indicators": {
        "rsi_period": 14,
        "macd_fast": 12,
        "macd_slow": 26,
        "macd_signal": 9,
    },
    "universe": {
        "min_market_cap_usd": 10_000_000_000,
        "min_price_usd": 10,
        "min_average_volume": 1_000_000,
        "min_average_dollar_volume": 100_000_000,
        "min_analysts": 8,
        "allowed_exchanges": ["NYSE", "NASDAQ"],
        "allowed_security_types": ["COMMON_STOCK"],
    },
    "spread": {
        "hard_max_spread_pct": 0.15,
        "low_risk_preferred_max": 0.05,
        "medium_risk_preferred_max": 0.10,
        "high_risk_max": 0.15,
    },
    "scoring": {
        "minimum_general": 78,
        "excellent": 88,
        "low_risk_min": 85,
        "medium_risk_min": 82,
        "high_risk_min": 78,
    },
    "risk": {
        "account_currency": "EUR",
        "account_value": 5000,
        "risk_pct": {"LOW": 0.25, "MEDIUM": 0.50, "HIGH": 0.75},
        "max_daily_risk_pct": 1.00,
        "allow_fractional_shares": False,
        "leverage": 1,
        "min_risk_reward": 1.5,
    },
    "setups": {
        "max_rsi5": 78,
        "ideal_rsi5_min": 55,
        "ideal_rsi5_max": 72,
        "max_distance_vwap_pct": 1.2,
        "max_atr_consumed_pct": 75,
        "min_rvol": 1.5,
        "breakout_buffer_pct": 0.05,
    },
    "sector_etfs": {
        "Communication Services": "XLC",
        "Consumer Discretionary": "XLY",
        "Consumer Staples": "XLP",
        "Energy": "XLE",
        "Financials": "XLF",
        "Health Care": "XLV",
        "Industrials": "XLI",
        "Materials": "XLB",
        "Real Estate": "XLRE",
        "Technology": "XLK",
        "Utilities": "XLU",
    },
    "output": {
        "snapshot": "alpha_intraday_snapshot.json",
        "journal": "alpha_intraday_journal.csv",
        "dashboard_dir": "docs/alpha",
    },
}


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(path: str | Path = "config_alpha_intraday.yaml") -> dict[str, Any]:
    data = {}
    p = Path(path)
    if p.exists():
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    config = deep_merge(DEFAULT_CONFIG, data)
    config["mode"] = os.getenv("ALPHA_MODE", config.get("mode", "development")).lower()
    live_env = os.getenv("ALPHA_LIVE_SIGNALS")
    if live_env is not None:
        config["live_signals"] = live_env.lower() == "true"
    provider_env = os.getenv("ALPHA_DATA_PROVIDER")
    if provider_env:
        config.setdefault("data", {})["provider"] = provider_env.lower()
    telegram_env = os.getenv("ALPHA_TELEGRAM_ENABLED")
    if telegram_env is not None:
        config["telegram_enabled"] = telegram_env.lower() == "true"
    feed_env = os.getenv("ALPACA_DATA_FEED")
    if feed_env:
        config.setdefault("data", {})["alpaca_feed"] = feed_env
    return config


def validate_config(config: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    mode = config.get("mode")
    if mode not in {AlphaMode.DEVELOPMENT.value, AlphaMode.PRODUCTION.value}:
        errors.append("mode debe ser development o production")
    if float(config.get("risk", {}).get("leverage", 1)) != 1:
        errors.append("Alpha Intradia no permite apalancamiento: risk.leverage debe ser 1")
    if config.get("live_signals") and mode != AlphaMode.PRODUCTION.value:
        errors.append("live_signals solo puede ser true en production")
    if float(config.get("risk", {}).get("min_risk_reward", 0)) < 1.5:
        errors.append("risk.min_risk_reward debe ser >= 1.5")
    return errors


def live_signal_allowed(config: dict[str, Any], quality_ok: bool, production_ready: bool) -> bool:
    return (
        config.get("mode") == AlphaMode.PRODUCTION.value
        and bool(config.get("live_signals"))
        and quality_ok
        and production_ready
    )
