from __future__ import annotations

import csv
from pathlib import Path


FIELDS = [
    "date", "ticker", "setup", "risk_category", "score", "entry_trigger", "theoretical_entry",
    "stop", "target1", "target2", "risk_reward", "result", "mfe", "mae", "market_regime",
    "rvol", "spread", "catalyst", "analyst_upside", "reason", "invalidation", "timestamps",
]


def append_paper_observation(path: str | Path, row: dict) -> None:
    p = Path(path)
    exists = p.exists()
    with p.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if not exists:
            writer.writeheader()
        writer.writerow({k: row.get(k, "") for k in FIELDS})
