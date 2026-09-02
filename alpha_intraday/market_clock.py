from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from .models import MarketStatus


NY_TZ = ZoneInfo("America/New_York")


US_MARKET_HOLIDAYS_2026 = {
    date(2026, 1, 1),
    date(2026, 1, 19),
    date(2026, 2, 16),
    date(2026, 4, 3),
    date(2026, 5, 25),
    date(2026, 6, 19),
    date(2026, 7, 3),
    date(2026, 9, 7),
    date(2026, 11, 26),
    date(2026, 12, 25),
}


@dataclass(frozen=True)
class MarketClockState:
    now_et: datetime
    status: MarketStatus
    is_session_day: bool
    new_entry_allowed: bool
    seconds_to_regular_open: int | None
    reason: str


def to_et(now: datetime | None = None) -> datetime:
    now = now or datetime.now(tz=NY_TZ)
    if now.tzinfo is None:
        raise ValueError("now debe ser timezone-aware")
    return now.astimezone(NY_TZ)


def is_session_day(day: date) -> bool:
    return day.weekday() < 5 and day not in US_MARKET_HOLIDAYS_2026


def next_regular_open(now: datetime | None = None) -> datetime:
    cur = to_et(now)
    candidate = cur.replace(hour=9, minute=30, second=0, microsecond=0)
    if candidate <= cur:
        candidate = candidate + timedelta(days=1)
    while not is_session_day(candidate.date()):
        candidate = candidate + timedelta(days=1)
    return candidate


def classify_market_time(now: datetime | None = None) -> MarketClockState:
    cur = to_et(now)
    if not is_session_day(cur.date()):
        return MarketClockState(cur, MarketStatus.HOLIDAY, False, False, None, "Festivo o fin de semana USA")

    t = cur.time()
    open_time = time(9, 30)
    seconds_to_open = int((cur.replace(hour=9, minute=30, second=0, microsecond=0) - cur).total_seconds())
    if t < time(4, 0):
        return MarketClockState(cur, MarketStatus.CLOSED, True, False, seconds_to_open, "Mercado cerrado antes de premarket")
    if t < open_time:
        return MarketClockState(cur, MarketStatus.PREMARKET, True, False, seconds_to_open, "Premarket: solo preseleccion")
    if t < time(9, 40):
        return MarketClockState(cur, MarketStatus.OPENING, True, False, 0, "Apertura restrictiva")
    if t <= time(10, 15):
        return MarketClockState(cur, MarketStatus.SELECTION_WINDOW, True, True, 0, "Ventana principal 09:40-10:15 ET")
    if t < time(15, 30):
        return MarketClockState(cur, MarketStatus.ENTRY_CLOSED, True, False, 0, "Nuevas entradas cerradas despues de 10:15 ET")
    if t < time(16, 0):
        return MarketClockState(cur, MarketStatus.CLOSING, True, False, 0, "Cierre cercano: cerrar observaciones intradia")
    if t < time(20, 0):
        return MarketClockState(cur, MarketStatus.AFTER_HOURS, True, False, None, "After-hours")
    return MarketClockState(cur, MarketStatus.CLOSED, True, False, None, "Mercado cerrado")


def should_run_selection(now: datetime | None = None) -> bool:
    state = classify_market_time(now)
    t = state.now_et.time()
    return state.is_session_day and time(9, 25) <= t <= time(10, 20)
