from datetime import datetime
from zoneinfo import ZoneInfo

from alpha_intraday.config import DEFAULT_CONFIG
from alpha_intraday.session import run_session
from alpha_intraday.providers.replay import ReplayMarketDataProvider


def test_run_session_crosses_0940_with_fake_clock():
    config = dict(DEFAULT_CONFIG)
    config["output"] = {"snapshot": "/tmp/alpha_test_snapshot.json", "dashboard_dir": "/tmp/alpha_test_docs"}
    snapshots = run_session(
        config,
        start_now=datetime(2026, 7, 8, 9, 25, tzinfo=ZoneInfo("America/New_York")),
        cadence_seconds=900,
        max_iterations=3,
        sleeper=lambda _seconds: None,
    )
    statuses = [s.market_status.value for s in snapshots]
    assert "PREMARKET" in statuses
    assert "SELECTION_WINDOW" in statuses
    assert all(c.setup.status.value != "READY_SHORT" for s in snapshots for c in s.candidates)


def test_replay_provider_filters_chronologically():
    fixture = "tests/alpha_intraday/fixtures/session_sample"
    now = datetime(2026, 7, 8, 9, 40, tzinfo=ZoneInfo("America/New_York"))
    provider = ReplayMarketDataProvider(fixture, now)
    bars = provider.intraday_bars("NVDA", limit=100)
    assert bars
    assert max(bar.timestamp for bar in bars) <= now
