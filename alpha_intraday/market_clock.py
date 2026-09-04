from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from .models import MarketStatus
from .market_calendar import MarketCalendar, StaticMarketCalendar


NY_TZ = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class MarketClockState:
    now_et: datetime
    status: MarketStatus
    is_session_day: bool
    new_entry_allowed: bool
    seconds_to_regular_open: int | None
    reason: str
    calendar_source: str = "fallback_static"


def to_et(now: datetime | None = None) -> datetime:
    now = now or datetime.now(tz=NY_TZ)
    if now.tzinfo is None:
        raise ValueError("now debe ser timezone-aware")
    return now.astimezone(NY_TZ)


def is_session_day(day, calendar: MarketCalendar | None = None) -> bool:
    calendar = calendar or StaticMarketCalendar()
    return calendar.day(day).is_open


def next_regular_open(now: datetime | None = None, calendar: MarketCalendar | None = None) -> datetime:
    calendar = calendar or StaticMarketCalendar()
    cur = to_et(now)
    day = calendar.day(cur.date())
    candidate = cur.replace(hour=day.open_time.hour, minute=day.open_time.minute, second=0, microsecond=0)
    if candidate <= cur:
        candidate = candidate + timedelta(days=1)
    while not is_session_day(candidate.date(), calendar):
        candidate = candidate + timedelta(days=1)
    return candidate


def classify_market_time(now: datetime | None = None, calendar: MarketCalendar | None = None) -> MarketClockState:
    calendar = calendar or StaticMarketCalendar()
    cur = to_et(now)
    calendar_day = calendar.day(cur.date())
    if not calendar_day.is_open:
        return MarketClockState(cur, MarketStatus.HOLIDAY, False, False, None, "Festivo o fin de semana USA", calendar_day.source)

    t = cur.time()
    open_time = calendar_day.open_time
    close_time = calendar_day.close_time
    seconds_to_open = int((cur.replace(hour=open_time.hour, minute=open_time.minute, second=0, microsecond=0) - cur).total_seconds())
    if t < time(4, 0):
        return MarketClockState(cur, MarketStatus.CLOSED, True, False, seconds_to_open, "Mercado cerrado antes de premarket", calendar_day.source)
    if t < open_time:
        return MarketClockState(cur, MarketStatus.PREMARKET, True, False, seconds_to_open, "Premarket: solo preseleccion", calendar_day.source)
    if t < time(9, 40):
        return MarketClockState(cur, MarketStatus.OPENING, True, False, 0, "Apertura restrictiva", calendar_day.source)
    if t <= time(10, 15):
        return MarketClockState(cur, MarketStatus.SELECTION_WINDOW, True, True, 0, "Ventana principal 09:40-10:15 ET", calendar_day.source)
    if t < min(time(15, 30), close_time):
        return MarketClockState(cur, MarketStatus.ENTRY_CLOSED, True, False, 0, "Nuevas entradas cerradas despues de 10:15 ET", calendar_day.source)
    if t < close_time:
        return MarketClockState(cur, MarketStatus.CLOSING, True, False, 0, "Cierre cercano: cerrar observaciones intradia", calendar_day.source)
    if t < time(20, 0):
        return MarketClockState(cur, MarketStatus.AFTER_HOURS, True, False, None, "After-hours", calendar_day.source)
    return MarketClockState(cur, MarketStatus.CLOSED, True, False, None, "Mercado cerrado", calendar_day.source)


def should_run_selection(now: datetime | None = None, calendar: MarketCalendar | None = None) -> bool:
    state = classify_market_time(now, calendar)
    t = state.now_et.time()
    return state.is_session_day and time(9, 25) <= t <= time(10, 20)
