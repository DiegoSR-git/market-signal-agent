from __future__ import annotations

import time
from datetime import datetime, timedelta, time as dtime
from zoneinfo import ZoneInfo

from .market_clock import classify_market_time, should_run_selection
from .signal_engine import run_alpha
from .telegram import send_alpha_telegram


def run_session(
    config: dict,
    *,
    start_now: datetime | None = None,
    cadence_seconds: int | None = None,
    telegram_enabled: bool = False,
    force: bool = False,
    sleeper=time.sleep,
    max_iterations: int | None = None,
):
    cadence = cadence_seconds or int(config.get("session", {}).get("cadence_seconds", 60))
    now = start_now
    snapshots = []
    if not force and not should_run_selection(now):
        return snapshots
    iteration = 0
    while True:
        current = now or datetime.now(ZoneInfo("America/New_York"))
        state = classify_market_time(current)
        if not force and not should_run_selection(current):
            break
        snapshot = run_alpha(config, now=current)
        snapshots.append(snapshot)
        if telegram_enabled:
            send_alpha_telegram(snapshot, force=force)
        iteration += 1
        if max_iterations is not None and iteration >= max_iterations:
            break
        if state.now_et.time() >= dtime(10, 20):
            break
        if now is not None:
            now = now + timedelta(seconds=cadence)
        else:
            sleeper(cadence)
    return snapshots
