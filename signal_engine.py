#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import hashlib
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import yaml

from dashboard_utils import esc, fmt_pct, fmt_price, render_page, score_class
from premium_agent_utils import market_metrics, safe_float


UNIFIED_SIGNALS_FILE = Path("unified_signals.json")
DECISION_SNAPSHOT_FILE = Path("decision_engine_snapshot.json")
PERFORMANCE_FILE = Path("signal_performance.json")
PERFORMANCE_DASHBOARD = Path("docs/performance_dashboard.html")


PREMIUM_SOURCES = [
    ("sec_filing", "SEC e insiders", "sec_filing_snapshot.json", "sec_filing_dashboard.html"),
    ("macro_regime", "Regimen macro", "macro_regime_snapshot.json", "macro_regime_dashboard.html"),
    ("sector_rotation", "Rotacion sectorial", "sector_rotation_snapshot.json", "sector_rotation_dashboard.html"),
    ("defi_liquidity", "Liquidez DeFi", "defi_liquidity_snapshot.json", "defi_liquidity_dashboard.html"),
    ("earnings_catalyst", "Catalizadores de resultados", "earnings_catalyst_snapshot.json", "earnings_catalyst_dashboard.html"),
    ("cftc_positioning", "Posicionamiento CFTC", "cftc_positioning_snapshot.json", "cftc_positioning_dashboard.html"),
    ("unusual_volume", "Volumen inusual", "unusual_volume_snapshot.json", "unusual_volume_dashboard.html"),
    ("altcoin_fundamentals", "Fundamentales altcoin", "altcoin_fundamentals_snapshot.json", "altcoin_fundamentals_dashboard.html"),
    ("intraday_cashout", "Intradia", "intraday_cashout_snapshot.json", "intraday_cashout_dashboard.html"),
]


def utc_now():
    return datetime.now(timezone.utc)


def iso_now():
    return utc_now().isoformat()


def read_json(path, default):
    p = Path(path)
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def load_yaml(path):
    p = Path(path)
    if not p.exists():
        return {}
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def as_items(value):
    if isinstance(value, list):
        return [x for x in value if isinstance(x, dict)]
    if isinstance(value, dict):
        for key in ("items", "results", "signals", "opportunities", "events"):
            if isinstance(value.get(key), list):
                return [x for x in value[key] if isinstance(x, dict)]
    return []


def parse_time(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def first_number(*values):
    for value in values:
        number = safe_float(value)
        if number is not None:
            return number
    return None


def signal_id(agent, asset, timestamp, signal_type, title):
    raw = "|".join(str(x or "") for x in [agent, asset, timestamp, signal_type, title])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def infer_direction(item):
    metrics = item.get("metrics", {}) if isinstance(item.get("metrics"), dict) else {}
    direction = str(metrics.get("direction") or item.get("direction") or "").upper()
    if direction in {"LONG", "SHORT", "WAIT"}:
        return direction
    title = str(item.get("title") or item.get("event_name") or "").lower()
    summary = str(item.get("summary") or "").lower()
    text = f"{title} {summary}"
    if any(x in text for x in ["short", "weakness", "risk-off", "fade"]):
        return "SHORT"
    if any(x in text for x in ["long", "continuation", "breakout", "rotacion", "volumen", "catalizador"]):
        return "LONG"
    return "WAIT"


def confidence_from_score(score):
    score = safe_float(score, 0)
    if score >= 85:
        return "alta"
    if score >= 75:
        return "media-alta"
    if score >= 65:
        return "media"
    return "baja"


def valid_until(timestamp, horizon):
    ts = parse_time(timestamp)
    if not ts:
        return None
    if horizon == "intraday":
        return ts.replace(hour=22, minute=0, second=0, microsecond=0).isoformat()
    if horizon == "swing":
        return (ts + timedelta(days=10)).isoformat()
    return (ts + timedelta(days=3)).isoformat()


def normalize_signal(agent, source_label, item, href):
    metrics = item.get("metrics", {}) if isinstance(item.get("metrics"), dict) else {}
    asset = item.get("asset") or item.get("ticker") or metrics.get("symbol")
    if not asset:
        return None
    timestamp = item.get("time_utc") or item.get("timestamp") or metrics.get("quote_timestamp") or iso_now()
    score = safe_float(item.get("score"), 0)
    signal_type = metrics.get("setup") or item.get("opportunity_type") or item.get("title") or agent
    horizon = "intraday" if agent == "intraday_cashout" else "swing"
    title = item.get("title") or item.get("event_name") or f"{asset} {source_label}"
    price = first_number(
        metrics.get("current_price"),
        metrics.get("price"),
        metrics.get("intraday_entry_reference"),
        item.get("market", {}).get("price") if isinstance(item.get("market"), dict) else None,
    )
    direction = infer_direction(item)
    status = metrics.get("action_state") or metrics.get("validation_status") or item.get("level") or "WATCH"
    signal = {
        "id": signal_id(agent, asset, timestamp, signal_type, title),
        "asset": str(asset).upper(),
        "agent": agent,
        "source_label": source_label,
        "score": round(score, 2),
        "confidence": confidence_from_score(score),
        "timestamp": timestamp,
        "valid_until": valid_until(timestamp, horizon),
        "horizon": horizon,
        "signal_type": str(signal_type),
        "direction": direction,
        "status": status,
        "title": str(title),
        "summary": item.get("summary") or item.get("ai_brief") or "",
        "entry_price": price,
        "stop_loss": first_number(metrics.get("stop_loss"), metrics.get("intraday_stop")),
        "take_profit": first_number(metrics.get("take_profit"), metrics.get("intraday_target")),
        "risk_reward": first_number(metrics.get("risk_reward"), metrics.get("risk_plan", {}).get("net_risk_reward") if isinstance(metrics.get("risk_plan"), dict) else None),
        "reasons": item.get("reasons") or item.get("score_reasons") or [],
        "source": item.get("source") or ((item.get("articles") or [{}])[0].get("url") if isinstance(item.get("articles"), list) else None),
        "dashboard": href,
        "metrics": metrics,
    }
    return signal


def collect_unified_signals():
    signals = []
    state = read_json("state.json", {})
    for item in as_items(state.get("last_snapshot", {}).get("stocks", {}).get("top", [])):
        signals.append(
            normalize_signal(
                "market_signal",
                "Bolsa / ETFs",
                {
                    "asset": item.get("symbol"),
                    "score": item.get("score"),
                    "title": f"{item.get('symbol')} oportunidad tecnica",
                    "summary": "; ".join(item.get("reasons", [])),
                    "reasons": item.get("reasons", []),
                    "metrics": item,
                    "time_utc": state.get("last_run_utc"),
                },
                "dashboard.html",
            )
        )
    for item in as_items(read_json("event_rumor_snapshot.json", [])):
        signals.append(normalize_signal("event_rumor", "Rumores y eventos", item, "event_rumor_dashboard.html"))
    for agent, label, path, href in PREMIUM_SOURCES:
        for item in as_items(read_json(path, [])):
            signals.append(normalize_signal(agent, label, item, href))
    signals = [x for x in signals if x]
    return sorted(signals, key=lambda x: (safe_float(x.get("score"), 0), x.get("timestamp") or ""), reverse=True)


def decision_for_asset(asset, items):
    best = max(items, key=lambda x: safe_float(x.get("score"), 0))
    agents = sorted({x.get("agent") for x in items})
    avg_score = sum(safe_float(x.get("score"), 0) for x in items) / len(items)
    directions = [x.get("direction") for x in items]
    long_votes = directions.count("LONG")
    short_votes = directions.count("SHORT")
    intraday = next((x for x in items if x.get("agent") == "intraday_cashout"), None)
    invalid_intraday = intraday and str(intraday.get("status", "")).upper() in {"NO_TRADE", "INVALID", "STALE_DATA", "LOW_VOLUME", "SPREAD_TOO_WIDE"}
    if invalid_intraday:
        decision = "NO_TRADE_INTRADIA"
    elif intraday and str(intraday.get("status", "")).upper() in {"READY_LONG", "READY_SHORT"}:
        decision = "INTRADAY_READY"
    elif avg_score >= 78 and len(agents) >= 2 and long_votes >= short_votes:
        decision = "BUY_WATCH"
    elif avg_score >= 70 and len(agents) >= 2:
        decision = "WATCHLIST"
    elif short_votes > long_votes and avg_score >= 70:
        decision = "RISK_OFF"
    else:
        decision = "LOW_PRIORITY"
    return {
        "asset": asset,
        "decision": decision,
        "score": round(avg_score, 2),
        "best_score": best.get("score"),
        "best_agent": best.get("agent"),
        "agents": agents,
        "signals": len(items),
        "direction_bias": "LONG" if long_votes > short_votes else "SHORT" if short_votes > long_votes else "MIXED",
        "top_summary": best.get("summary", "")[:280],
        "updated_utc": iso_now(),
    }


def build_decisions(signals):
    grouped = {}
    for signal in signals:
        grouped.setdefault(signal["asset"], []).append(signal)
    decisions = [decision_for_asset(asset, items) for asset, items in grouped.items()]
    return sorted(decisions, key=lambda x: (x["decision"] == "INTRADAY_READY", x["score"]), reverse=True)


def evaluate_performance(signals, config):
    perf = read_json(PERFORMANCE_FILE, {"signals": {}, "summary": {}})
    records = perf.setdefault("signals", {})
    max_eval = int(config.get("performance", {}).get("max_price_fetches", 25))
    min_score = safe_float(config.get("performance", {}).get("min_score_to_track"), 50)
    fetched = 0
    for signal in signals:
        if safe_float(signal.get("score"), 0) < min_score:
            continue
        sid = signal["id"]
        rec = records.setdefault(
            sid,
            {
                "id": sid,
                "asset": signal["asset"],
                "agent": signal["agent"],
                "signal_type": signal["signal_type"],
                "direction": signal["direction"],
                "score": signal["score"],
                "entry_price": signal.get("entry_price"),
                "timestamp": signal.get("timestamp"),
                "valid_until": signal.get("valid_until"),
                "observations": {},
                "status": "OPEN",
            },
        )
        entry = safe_float(rec.get("entry_price"))
        if entry is None:
            continue
        if fetched >= max_eval:
            continue
        metrics = market_metrics(signal["asset"], config={})
        price = safe_float(metrics.get("price"))
        if price is None:
            continue
        fetched += 1
        ret = (price / entry - 1) * 100
        if rec.get("direction") == "SHORT":
            ret *= -1
        rec["last_price"] = price
        rec["last_return_pct"] = ret
        rec["last_checked_utc"] = iso_now()
        rec["observations"]["latest"] = {"time_utc": iso_now(), "price": price, "return_pct": ret}
        tp = safe_float(signal.get("take_profit"))
        sl = safe_float(signal.get("stop_loss"))
        if rec.get("direction") == "LONG" and tp and price >= tp:
            rec["status"] = "TP_HIT"
        elif rec.get("direction") == "LONG" and sl and price <= sl:
            rec["status"] = "SL_HIT"
        elif rec.get("direction") == "SHORT" and tp and price <= tp:
            rec["status"] = "TP_HIT"
        elif rec.get("direction") == "SHORT" and sl and price >= sl:
            rec["status"] = "SL_HIT"
        elif parse_time(signal.get("valid_until")) and utc_now() > parse_time(signal.get("valid_until")):
            rec["status"] = "EXPIRED"
    closed = [x for x in records.values() if x.get("last_return_pct") is not None]
    wins = [x for x in closed if safe_float(x.get("last_return_pct"), 0) > 0]
    perf["summary"] = {
        "total_tracked": len(records),
        "with_price": len(closed),
        "win_rate": round(len(wins) / len(closed) * 100, 2) if closed else None,
        "avg_return_pct": round(sum(safe_float(x.get("last_return_pct"), 0) for x in closed) / len(closed), 2) if closed else None,
        "updated_utc": iso_now(),
    }
    write_json(PERFORMANCE_FILE, perf)
    return perf


def render_performance_dashboard(signals, decisions, performance):
    summary = performance.get("summary", {})
    decision_rows = "".join(
        f"""<tr>
          <td><div class="company">{esc(x.get('asset'))}</div><div class="muted">{esc(', '.join(x.get('agents', [])))}</div></td>
          <td><span class="pill {score_class(x.get('score'))}">{esc(x.get('decision'))}</span></td>
          <td>{esc(x.get('score'))}</td>
          <td>{esc(x.get('direction_bias'))}</td>
          <td>{esc(x.get('top_summary'))}</td>
        </tr>"""
        for x in decisions[:40]
    )
    perf_rows = "".join(
        f"""<tr>
          <td><div class="company">{esc(x.get('asset'))}</div><div class="muted">{esc(x.get('agent'))}</div></td>
          <td>{esc(x.get('status'))}</td>
          <td>{esc(x.get('direction'))}</td>
          <td>{fmt_price(x.get('entry_price'))}</td>
          <td>{fmt_price(x.get('last_price'))}</td>
          <td>{fmt_pct(x.get('last_return_pct'))}</td>
        </tr>"""
        for x in sorted(performance.get("signals", {}).values(), key=lambda r: str(r.get("last_checked_utc", "")), reverse=True)[:50]
    )
    body = f"""<div class="shell">
  <div class="topbar">
    <div>
      <h1>Motor De Decisión Y Rendimiento</h1>
      <div class="muted">Señales normalizadas, decisión agregada y seguimiento de resultados.</div>
    </div>
    <nav class="nav">
      <a class="btn primary" href="opportunities.html">Oportunidades Claras</a>
      <a class="btn" href="index.html">Resumen</a>
      <a class="btn" href="intraday_cashout_dashboard.html">Intradia</a>
      <a class="btn" href="https://github.com/DiegoSR-git/market-signal-agent/actions">Actions</a>
    </nav>
  </div>
  <section class="grid">
    <div class="card span-3"><h3>Señales</h3><div class="metric">{len(signals)}</div><div class="submetric">normalizadas</div></div>
    <div class="card span-3"><h3>Activos</h3><div class="metric">{len(decisions)}</div><div class="submetric">con decisión agregada</div></div>
    <div class="card span-3"><h3>Win Rate</h3><div class="metric">{fmt_pct(summary.get('win_rate'), 1, signed=False)}</div><div class="submetric">sobre señales con precio</div></div>
    <div class="card span-3"><h3>Retorno Medio</h3><div class="metric">{fmt_pct(summary.get('avg_return_pct'))}</div><div class="submetric">estimado</div></div>
    <div class="card span-12">
      <h2>Decisión Agregada</h2>
      <p class="intro">Combina las señales de todos los agentes y prioriza lo que merece atención real.</p>
      <div class="table-wrap"><table><thead><tr><th>Activo</th><th>Decisión</th><th>Score</th><th>Sesgo</th><th>Resumen</th></tr></thead><tbody>{decision_rows or '<tr><td colspan="5">Sin decisiones disponibles</td></tr>'}</tbody></table></div>
    </div>
    <div class="card span-12">
      <h2>Tracking De Señales</h2>
      <p class="intro">Seguimiento aproximado frente al último precio disponible para aprender qué agentes y setups aportan valor.</p>
      <div class="table-wrap"><table><thead><tr><th>Activo</th><th>Estado</th><th>Dirección</th><th>Entrada</th><th>Último</th><th>Retorno</th></tr></thead><tbody>{perf_rows or '<tr><td colspan="6">Sin tracking todavía</td></tr>'}</tbody></table></div>
    </div>
  </section>
  <footer>Generado: {utc_now().strftime('%Y-%m-%d %H:%M UTC')}. No es asesoramiento financiero personalizado.</footer>
</div>"""
    PERFORMANCE_DASHBOARD.write_text(render_page("Motor De Decisión Y Rendimiento", body), encoding="utf-8")


def run_engine(config_path="config_signal_engine.yaml", max_price_fetches=None):
    config = load_yaml(config_path)
    if max_price_fetches is not None:
        config.setdefault("performance", {})["max_price_fetches"] = max(0, int(max_price_fetches))
    signals = collect_unified_signals()
    decisions = build_decisions(signals)
    performance = evaluate_performance(signals, config)
    write_json(UNIFIED_SIGNALS_FILE, signals)
    write_json(DECISION_SNAPSHOT_FILE, decisions)
    render_performance_dashboard(signals, decisions, performance)
    return signals, decisions, performance


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config_signal_engine.yaml")
    parser.add_argument(
        "--max-price-fetches",
        type=int,
        default=None,
        help="Limita las consultas de precios en vivo para seguimiento de rendimiento.",
    )
    parser.add_argument(
        "--skip-price-fetches",
        action="store_true",
        help="Genera señales, decisiones y dashboard sin consultar precios en vivo.",
    )
    args = parser.parse_args()
    max_price_fetches = 0 if args.skip_price_fetches else args.max_price_fetches
    signals, decisions, performance = run_engine(args.config, max_price_fetches=max_price_fetches)
    print(f"Señales normalizadas: {len(signals)}")
    print(f"Decisiones: {len(decisions)}")
    print(f"Tracking: {performance.get('summary', {})}")


if __name__ == "__main__":
    main()
