from datetime import datetime
from zoneinfo import ZoneInfo

from alpha_intraday.market_clock import classify_market_time, should_run_selection
from alpha_intraday.market_calendar import StaticMarketCalendar
from alpha_intraday.models import MarketStatus


def dt(hour, minute):
    return datetime(2026, 7, 8, hour, minute, tzinfo=ZoneInfo("America/New_York"))


def test_market_clock_uses_new_york_windows():
    assert classify_market_time(dt(9, 20)).status == MarketStatus.PREMARKET
    assert classify_market_time(dt(9, 35)).status == MarketStatus.OPENING
    assert classify_market_time(dt(9, 45)).status == MarketStatus.SELECTION_WINDOW
    assert classify_market_time(dt(10, 16)).status == MarketStatus.ENTRY_CLOSED
    assert should_run_selection(dt(9, 25)) is True
    assert should_run_selection(dt(10, 21)) is False


def test_market_clock_holiday_weekend():
    saturday = datetime(2026, 7, 11, 9, 45, tzinfo=ZoneInfo("America/New_York"))
    assert classify_market_time(saturday).status == MarketStatus.HOLIDAY


def test_market_calendar_early_close_and_dst():
    calendar = StaticMarketCalendar()
    assert calendar.day(datetime(2026, 11, 27, tzinfo=ZoneInfo("America/New_York")).date()).early_close is True
    summer = datetime(2026, 7, 8, 9, 45, tzinfo=ZoneInfo("America/New_York"))
    winter = datetime(2026, 1, 20, 9, 45, tzinfo=ZoneInfo("America/New_York"))
    assert classify_market_time(summer).status == MarketStatus.SELECTION_WINDOW
    assert classify_market_time(winter).status == MarketStatus.SELECTION_WINDOW
