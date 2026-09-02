from __future__ import annotations

import hashlib
import json
from pathlib import Path

from premium_agent_utils import send_telegram


STATE_FILE = Path("alpha_intraday_telegram_state.json")


def signal_transition_id(symbol: str, old_status: str, new_status: str, setup: str) -> str:
    raw = f"{symbol}|{old_status}|{new_status}|{setup}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def alpha_message(snapshot) -> str:
    mode = snapshot.data_mode.value.upper()
    best = snapshot.best_operation
    if not best:
        return (
            f"<b>ALPHA INTRADIA - {mode}</b>\n"
            f"Veredicto: <b>NO OPERAR</b>\n"
            f"Mercado: {snapshot.market_status.value}\n"
            f"Motivos: {'; '.join(snapshot.blocking_reasons[:5])}\n\n"
            "DEVELOPMENT - no senal real."
        )
    return (
        f"<b>ALPHA INTRADIA - {mode}</b>\n"
        f"{best.symbol}\n"
        f"Riesgo: {best.score.risk_category.value}\n"
        f"Score: {best.score.total}/100\n"
        f"Estado: {best.setup.status.value}\n"
        f"Entrada: {best.setup.entry_zone}\n"
        f"Stop: {best.setup.stop}\n"
        f"T1: {best.setup.target1}\n"
        f"B/R: {best.setup.risk_reward1}\n"
        f"Datos: {best.quote.provider if best.quote else 'N/A'} {best.quote.feed if best.quote else ''}\n\n"
        "DEVELOPMENT - no senal real."
    )


def send_alpha_telegram(snapshot, force: bool = False) -> bool:
    state = load_state()
    best = snapshot.best_operation
    symbol = best.symbol if best else "SYSTEM"
    new_status = best.setup.status.value if best else "NO_TRADE"
    key = signal_transition_id(symbol, state.get(symbol, "UNKNOWN"), new_status, best.setup.setup_type.value if best else "NO_SETUP")
    if not force and state.get("last_key") == key:
        return False
    send_telegram(alpha_message(snapshot))
    state[symbol] = new_status
    state["last_key"] = key
    save_state(state)
    return True
