from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class AlphaMode(str, Enum):
    DEVELOPMENT = "development"
    PRODUCTION = "production"


class MarketStatus(str, Enum):
    CLOSED = "CLOSED"
    PREMARKET = "PREMARKET"
    OPENING = "OPENING"
    SELECTION_WINDOW = "SELECTION_WINDOW"
    ENTRY_CLOSED = "ENTRY_CLOSED"
    REGULAR_SESSION = "REGULAR_SESSION"
    CLOSING = "CLOSING"
    AFTER_HOURS = "AFTER_HOURS"
    HOLIDAY = "HOLIDAY"


class SignalStatus(str, Enum):
    PREMARKET = "PREMARKET"
    PRESELECTED = "PRESELECTED"
    WAIT = "WAIT"
    READY_LONG = "READY_LONG"
    ACTIVE_OBSERVATION = "ACTIVE_OBSERVATION"
    INVALIDATED = "INVALIDATED"
    EXPIRED = "EXPIRED"
    CLOSED = "CLOSED"
    NO_TRADE = "NO_TRADE"
    DATA_BLOCKED = "DATA_BLOCKED"


class RiskCategory(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    NONE = "NONE"


class SetupType(str, Enum):
    BREAKOUT = "BREAKOUT"
    VWAP_RECLAIM = "VWAP_RECLAIM"
    CONTROLLED_PULLBACK = "CONTROLLED_PULLBACK"
    NO_SETUP = "NO_SETUP"


class HealthStatus(str, Enum):
    GREEN = "GREEN"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    FIXTURE = "FIXTURE"


class ReadinessStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_CONFIGURED = "NOT_CONFIGURED"


class Regime(str, Enum):
    BULLISH = "BULLISH"
    WEAK_BULLISH = "WEAK_BULLISH"
    NEUTRAL = "NEUTRAL"
    WEAK_BEARISH = "WEAK_BEARISH"
    BEARISH = "BEARISH"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    BINARY_EVENT = "BINARY_EVENT"


@dataclass(frozen=True)
class TimedValue:
    value: float | str | None
    provider: str
    source_timestamp: datetime | None
    received_at: datetime
    quality_status: str = "OK"


@dataclass(frozen=True)
class Quote:
    symbol: str
    bid: float | None
    ask: float | None
    bid_size: float | None
    ask_size: float | None
    timestamp: datetime | None
    provider: str
    feed: str


@dataclass(frozen=True)
class Bar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class SecurityMetadata:
    symbol: str
    company: str
    exchange: str
    security_type: str
    market_cap: float | None
    average_volume: float | None
    average_dollar_volume: float | None
    sector: str | None = None
    industry: str | None = None
    active: bool = True
    tradable: bool = True
    source: str = "fixture"
    updated_at: datetime | None = None


@dataclass(frozen=True)
class AnalystSnapshot:
    symbol: str
    analyst_count: int | None
    strong_buy: int | None = None
    buy: int | None = None
    hold: int | None = None
    sell: int | None = None
    strong_sell: int | None = None
    target_median: float | None = None
    target_mean: float | None = None
    target_low: float | None = None
    target_high: float | None = None
    median_target_available: bool = False
    source: str = "not_configured"
    as_of: datetime | None = None


@dataclass(frozen=True)
class CatalystSnapshot:
    symbol: str
    classification: str
    title: str = ""
    source: str = "not_configured"
    as_of: datetime | None = None
    confirmed_by_price_volume: bool = False


@dataclass(frozen=True)
class MarketRegimeSnapshot:
    regime: Regime
    spy_change_pct: float | None = None
    qqq_change_pct: float | None = None
    vix: float | None = None
    us10y: float | None = None
    actual_index_verified: bool = False
    reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ReadinessCheck:
    name: str
    status: ReadinessStatus
    critical: bool
    reason: str


@dataclass(frozen=True)
class ProductionReadinessReport:
    production_ready: bool
    checks: list[ReadinessCheck]

    def blocking_reasons(self) -> list[str]:
        return [
            f"{check.name}: {check.status.value} - {check.reason}"
            for check in self.checks
            if check.critical and check.status != ReadinessStatus.PASS
        ]


@dataclass(frozen=True)
class ScoreComponent:
    name: str
    score: float
    max_score: float
    reasons_positive: list[str] = field(default_factory=list)
    reasons_negative: list[str] = field(default_factory=list)
    missing_data: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AlphaScore:
    total: float
    components: list[ScoreComponent]
    risk_category: RiskCategory
    candidate_valid: bool
    blocking_reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SetupPlan:
    setup_type: SetupType
    status: SignalStatus
    trigger: str
    entry_zone: str
    activation_conditions: list[str]
    invalidation: str
    stop: float | None
    target1: float | None
    target2: float | None
    risk_reward1: float | None
    risk_reward2: float | None
    expires_at: datetime | None
    evidence: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RiskPlan:
    account_currency: str
    risk_category: RiskCategory
    risk_eur: float
    risk_usd: float | None
    shares: int | None
    notional_usd: float | None
    max_daily_risk_eur: float
    position_size_available: bool
    blocking_reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AlphaCandidate:
    symbol: str
    company: str
    price: float | None
    quote: Quote | None
    metadata: SecurityMetadata
    analysts: AnalystSnapshot | None
    catalyst: CatalystSnapshot | None
    metrics: dict[str, Any]
    data_quality: dict[str, Any]
    score: AlphaScore
    setup: SetupPlan
    risk: RiskPlan | None


@dataclass(frozen=True)
class AlphaSnapshot:
    analysis_timestamp: datetime
    timezone: str
    market_status: MarketStatus
    data_mode: AlphaMode
    data_feed: str
    provider_health: dict[str, str]
    production_readiness: ProductionReadinessReport
    market_regime: MarketRegimeSnapshot
    candidates: list[AlphaCandidate]
    best_operation: AlphaCandidate | None
    signal_allowed: bool
    blocking_reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        def convert(value: Any) -> Any:
            if isinstance(value, Enum):
                return value.value
            if isinstance(value, datetime):
                return value.isoformat()
            if isinstance(value, list):
                return [convert(x) for x in value]
            if isinstance(value, dict):
                return {k: convert(v) for k, v in value.items()}
            if hasattr(value, "__dataclass_fields__"):
                return convert(asdict(value))
            if hasattr(value, "item"):
                try:
                    return convert(value.item())
                except Exception:
                    pass
            return value

        return convert(self)
