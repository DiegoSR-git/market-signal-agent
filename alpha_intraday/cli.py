from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import load_config, validate_config
from .market_clock import classify_market_time, should_run_selection
from .signal_engine import render_text, run_alpha
from .telegram import send_alpha_telegram


def cmd_validate_config(args) -> int:
    config = load_config(args.config)
    errors = validate_config(config)
    if errors:
        print("\n".join(errors))
        return 1
    print("config ok")
    return 0


def cmd_health(args) -> int:
    config = load_config(args.config)
    clock = classify_market_time()
    print(json.dumps({"config_errors": validate_config(config), "market": clock.__dict__}, default=str, indent=2))
    return 0


def cmd_snapshot(args) -> int:
    config = load_config(args.config)
    now = datetime.fromisoformat(args.now).astimezone(ZoneInfo("America/New_York")) if args.now else None
    snapshot = run_alpha(config, now=now)
    print(render_text(snapshot))
    if args.telegram:
        send_alpha_telegram(snapshot, force=args.force)
    return 0


def cmd_preselect(args) -> int:
    config = load_config(args.config)
    snapshot = run_alpha(config)
    print(render_text(snapshot))
    return 0


def cmd_run_session(args) -> int:
    now = datetime.fromisoformat(args.now).astimezone(ZoneInfo("America/New_York")) if args.now else None
    if not args.force and not should_run_selection(now):
        print("Fuera de ventana valida Alpha. Salida sin cambios operativos.")
        return 0
    return cmd_snapshot(args)


def cmd_replay(args) -> int:
    fixture = Path(args.fixture)
    now_file = fixture / "now.txt"
    now = now_file.read_text(encoding="utf-8").strip() if now_file.exists() else "2026-07-08T09:45:00-04:00"
    args.now = now
    return cmd_snapshot(args)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m alpha_intraday.cli")
    parser.add_argument("--config", default="config_alpha_intraday.yaml")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate-config").set_defaults(func=cmd_validate_config)
    sub.add_parser("health").set_defaults(func=cmd_health)
    p = sub.add_parser("snapshot")
    p.add_argument("--dry-run", action="store_true", default=True)
    p.add_argument("--telegram", action="store_true")
    p.add_argument("--force", action="store_true")
    p.add_argument("--now")
    p.set_defaults(func=cmd_snapshot)
    p = sub.add_parser("preselect")
    p.add_argument("--dry-run", action="store_true", default=True)
    p.set_defaults(func=cmd_preselect)
    p = sub.add_parser("run-session")
    p.add_argument("--dry-run", action="store_true", default=True)
    p.add_argument("--telegram", action="store_true")
    p.add_argument("--force", action="store_true")
    p.add_argument("--now")
    p.set_defaults(func=cmd_run_session)
    p = sub.add_parser("replay")
    p.add_argument("--fixture", required=True)
    p.add_argument("--telegram", action="store_true")
    p.add_argument("--force", action="store_true")
    p.add_argument("--now")
    p.set_defaults(func=cmd_replay)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
