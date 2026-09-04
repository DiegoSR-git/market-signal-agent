from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time


@dataclass(frozen=True)
class MarketCalendarDay:
    trading_day: date
    is_open: bool
    open_time: time = time(9, 30)
    close_time: time = time(16, 0)
    early_close: bool = False
    source: str = "fallback_static"


class MarketCalendar:
    name = "base"

    def day(self, trading_day: date) -> MarketCalendarDay:
        raise NotImplementedError


class StaticMarketCalendar(MarketCalendar):
    name = "fallback_static"

    HOLIDAYS = {
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
    EARLY_CLOSES = {
        date(2026, 11, 27): time(13, 0),
        date(2026, 12, 24): time(13, 0),
    }

    def day(self, trading_day: date) -> MarketCalendarDay:
        if trading_day.weekday() >= 5 or trading_day in self.HOLIDAYS:
            return MarketCalendarDay(trading_day, False, source=self.name)
        if trading_day in self.EARLY_CLOSES:
            return MarketCalendarDay(trading_day, True, close_time=self.EARLY_CLOSES[trading_day], early_close=True, source=self.name)
        return MarketCalendarDay(trading_day, True, source=self.name)
