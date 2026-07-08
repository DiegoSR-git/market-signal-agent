import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from signal_engine import decision_for_asset, normalize_signal


def test_normalize_intraday_signal_schema():
    signal = normalize_signal(
        "intraday_cashout",
        "Intradia",
        {
            "asset": "NVDA",
            "score": 88,
            "title": "NVDA READY_LONG LONG_CONTINUATION",
            "summary": "Setup validado",
            "time_utc": "2026-07-08T13:05:00+00:00",
            "metrics": {
                "current_price": 130,
                "setup": "LONG_CONTINUATION",
                "direction": "LONG",
                "stop_loss": 128,
                "take_profit": 133,
                "risk_reward": 1.5,
                "action_state": "READY_LONG",
            },
        },
        "intraday_cashout_dashboard.html",
    )
    assert signal["asset"] == "NVDA"
    assert signal["direction"] == "LONG"
    assert signal["horizon"] == "intraday"
    assert signal["entry_price"] == 130
    assert signal["status"] == "READY_LONG"


def test_decision_prefers_intraday_ready():
    decision = decision_for_asset(
        "NVDA",
        [
            {"asset": "NVDA", "agent": "intraday_cashout", "score": 86, "direction": "LONG", "status": "READY_LONG", "summary": "ready"},
            {"asset": "NVDA", "agent": "unusual_volume", "score": 75, "direction": "LONG", "summary": "volume"},
        ],
    )
    assert decision["decision"] == "INTRADAY_READY"


if __name__ == "__main__":
    test_normalize_intraday_signal_schema()
    test_decision_prefers_intraday_ready()
