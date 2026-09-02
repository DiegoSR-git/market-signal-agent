from __future__ import annotations

from .models import AnalystSnapshot, SecurityMetadata


def universe_filter_reason(meta: SecurityMetadata, analysts: AnalystSnapshot | None, price: float | None, config: dict) -> list[str]:
    reasons: list[str] = []
    uni = config.get("universe", {})
    if meta.exchange not in set(uni.get("allowed_exchanges", [])):
        reasons.append(f"exchange no permitido: {meta.exchange}")
    if meta.security_type not in set(uni.get("allowed_security_types", [])):
        reasons.append(f"tipo no permitido: {meta.security_type}")
    if not meta.active or not meta.tradable:
        reasons.append("activo no negociable")
    if meta.market_cap is None or meta.market_cap < uni.get("min_market_cap_usd", 10_000_000_000):
        reasons.append("market cap insuficiente o no verificada")
    if price is None or price <= uni.get("min_price_usd", 10):
        reasons.append("precio insuficiente o no verificado")
    if meta.average_volume is None or meta.average_volume < uni.get("min_average_volume", 1_000_000):
        reasons.append("volumen medio insuficiente")
    if meta.average_dollar_volume is None or meta.average_dollar_volume < uni.get("min_average_dollar_volume", 100_000_000):
        reasons.append("volumen monetario insuficiente")
    min_analysts = uni.get("min_analysts", 8)
    if analysts is None or analysts.analyst_count is None or analysts.analyst_count < min_analysts:
        reasons.append("analistas insuficientes")
    return reasons


def eligible_universe(metadata: list[SecurityMetadata], analyst_provider, quote_by_symbol: dict[str, float | None], config: dict):
    accepted = []
    rejected = {}
    for meta in metadata:
        analysts = analyst_provider.snapshot(meta.symbol) if analyst_provider else None
        reasons = universe_filter_reason(meta, analysts, quote_by_symbol.get(meta.symbol), config)
        if reasons:
            rejected[meta.symbol] = reasons
        else:
            accepted.append((meta, analysts))
    return accepted, rejected
