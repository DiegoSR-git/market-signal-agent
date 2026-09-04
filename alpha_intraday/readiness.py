from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import HealthStatus, ProductionReadinessReport, ReadinessCheck, ReadinessStatus


@dataclass(frozen=True)
class ProviderBundle:
    market_data: Any
    universe: Any
    analysts: Any
    news: Any
    macro: Any
    index_data: Any
    fx: Any
    storage: Any | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "market_data": self.market_data,
            "universe": self.universe,
            "analysts": self.analysts,
            "news": self.news,
            "macro": self.macro,
            "index_data": self.index_data,
            "fx": self.fx,
            "storage": self.storage,
        }


def provider_health(bundle: ProviderBundle) -> dict[str, str]:
    health: dict[str, str] = {}
    for name, provider in bundle.as_dict().items():
        if provider is None:
            health[name] = HealthStatus.NOT_CONFIGURED.value
            continue
        provider_name = getattr(provider, "name", "unknown")
        if provider_name in {"fixture", "mock"}:
            health[name] = HealthStatus.FIXTURE.value
        elif provider_name == "not_configured":
            health[name] = HealthStatus.NOT_CONFIGURED.value
        else:
            health[name] = HealthStatus.GREEN.value
    return health


def _check(name: str, ok: bool, reason: str, critical: bool = True, not_configured: bool = False) -> ReadinessCheck:
    status = ReadinessStatus.PASS if ok else (ReadinessStatus.NOT_CONFIGURED if not_configured else ReadinessStatus.FAIL)
    return ReadinessCheck(name, status, critical, reason)


def build_readiness_report(bundle: ProviderBundle, config: dict[str, Any], quality_ok: bool, market_data_sample: dict | None = None) -> ProductionReadinessReport:
    health = provider_health(bundle)
    sample = market_data_sample or {}
    feed = config.get("data", {}).get("alpaca_feed")
    checks = [
        _check("market_data_provider_real", health["market_data"] not in {HealthStatus.FIXTURE.value, HealthStatus.NOT_CONFIGURED.value}, health["market_data"]),
        _check("feed_correct", feed == "sip", f"feed={feed}; SIP requerido para produccion"),
        _check("quote_available", bool(sample.get("quote_available")), "quote verificada" if sample.get("quote_available") else "quote no verificada"),
        _check("bars_available", bool(sample.get("bars_available")), "bars verificadas" if sample.get("bars_available") else "bars no verificadas"),
        _check("universe_provider_real", health["universe"] == HealthStatus.GREEN.value, health["universe"]),
        _check("analysts_provider_real", health["analysts"] == HealthStatus.GREEN.value, health["analysts"], not_configured=health["analysts"] == HealthStatus.NOT_CONFIGURED.value),
        _check("macro_critical", health["macro"] == HealthStatus.GREEN.value, health["macro"], not_configured=health["macro"] == HealthStatus.NOT_CONFIGURED.value),
        _check("fx", health["fx"] == HealthStatus.GREEN.value, health["fx"], not_configured=health["fx"] == HealthStatus.NOT_CONFIGURED.value),
        _check("absence_of_fixtures", HealthStatus.FIXTURE.value not in health.values(), f"health={health}"),
        _check("freshness", bool(sample.get("freshness_ok")), "freshness ok" if sample.get("freshness_ok") else "freshness no verificada"),
        _check("quality_gate", quality_ok, "quality gate ok" if quality_ok else "quality gate bloqueado"),
    ]
    return ProductionReadinessReport(all(c.status == ReadinessStatus.PASS for c in checks if c.critical), checks)
