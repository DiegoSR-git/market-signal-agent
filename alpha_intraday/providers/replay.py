from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from alpha_intraday.models import AnalystSnapshot, Bar, CatalystSnapshot, Quote, SecurityMetadata


def parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(ZoneInfo("America/New_York"))


def read_json(path: Path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


class ReplayMarketDataProvider:
    name = "fixture"

    def __init__(self, fixture_dir: str | Path, now: datetime):
        self.fixture_dir = Path(fixture_dir)
        self.now = now.astimezone(ZoneInfo("America/New_York"))
        self.quotes = read_json(self.fixture_dir / "quotes.json", {})
        self.bars = read_json(self.fixture_dir / "bars_1m.json", {})
        self.metrics = read_json(self.fixture_dir / "synthetic_metrics.json", {})

    def latest_quote(self, symbol: str) -> Quote:
        rows = [x for x in self.quotes.get(symbol, []) if parse_dt(x["t"]) <= self.now]
        if not rows:
            return Quote(symbol, None, None, None, None, None, self.name, "fixture")
        raw = rows[-1]
        return Quote(symbol, raw.get("bid"), raw.get("ask"), raw.get("bid_size"), raw.get("ask_size"), parse_dt(raw["t"]), self.name, "fixture")

    def intraday_bars(self, symbol: str, timeframe: str = "1Min", limit: int = 120) -> list[Bar]:
        rows = [x for x in self.bars.get(symbol, []) if parse_dt(x["t"]) <= self.now]
        out = [
            Bar(parse_dt(x["t"]), float(x["open"]), float(x["high"]), float(x["low"]), float(x["close"]), float(x["volume"]))
            for x in rows[-limit:]
        ]
        if any(bar.timestamp > self.now for bar in out):
            raise AssertionError("Replay entrego barras futuras")
        return out

    def synthetic_metrics(self, symbol: str) -> dict:
        return self.metrics.get(symbol, {})


class ReplayUniverseProvider:
    name = "fixture"

    def __init__(self, fixture_dir: str | Path):
        self.metadata = read_json(Path(fixture_dir) / "metadata.json", [])

    def list_metadata(self) -> list[SecurityMetadata]:
        return [SecurityMetadata(**row) for row in self.metadata]


class ReplayAnalystProvider:
    name = "fixture"

    def __init__(self, fixture_dir: str | Path):
        self.data = read_json(Path(fixture_dir) / "analysts.json", {})

    def snapshot(self, symbol: str) -> AnalystSnapshot | None:
        row = self.data.get(symbol)
        return AnalystSnapshot(symbol=symbol, **row) if row else None


class ReplayNewsProvider:
    name = "fixture"

    def __init__(self, fixture_dir: str | Path):
        self.data = read_json(Path(fixture_dir) / "news.json", {})

    def latest_catalyst(self, symbol: str) -> CatalystSnapshot | None:
        row = self.data.get(symbol)
        return CatalystSnapshot(symbol=symbol, **row) if row else None


class ReplayMacroProvider:
    name = "fixture"

    def __init__(self, fixture_dir: str | Path):
        self.data = read_json(Path(fixture_dir) / "macro.json", {})

    def snapshot(self) -> dict:
        return self.data


class ReplayFXProvider:
    name = "fixture"

    def __init__(self, fixture_dir: str | Path):
        self.data = read_json(Path(fixture_dir) / "fx.json", {"eurusd": None, "source": "fixture"})

    def eurusd(self) -> tuple[float | None, str]:
        return self.data.get("eurusd"), self.data.get("source", "fixture")
