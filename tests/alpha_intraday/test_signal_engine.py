from datetime import datetime
from zoneinfo import ZoneInfo

from alpha_intraday.config import DEFAULT_CONFIG
from alpha_intraday.signal_engine import run_alpha


def test_development_blocks_live_signal_and_short_is_impossible(tmp_path):
    config = dict(DEFAULT_CONFIG)
    config["output"] = {"snapshot": str(tmp_path / "snapshot.json"), "dashboard_dir": str(tmp_path / "docs")}
    snapshot = run_alpha(config, now=datetime(2026, 7, 8, 9, 45, tzinfo=ZoneInfo("America/New_York")))
    assert snapshot.data_mode.value == "development"
    assert snapshot.signal_allowed is False
    assert all(c.setup.status.value != "READY_SHORT" for c in snapshot.candidates)
    assert (tmp_path / "snapshot.json").exists()
    assert (tmp_path / "docs" / "index.html").exists()
