import csv
import html
import json
from pathlib import Path
from datetime import datetime, timezone


def utc_now_label():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def esc(value):
    return html.escape("" if value is None else str(value))


def read_json(path, default):
    try:
        p = Path(path)
        if not p.exists():
            return default
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def read_csv_rows(path, limit=None):
    try:
        p = Path(path)
        if not p.exists():
            return []
        with p.open("r", encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        return rows[-limit:] if limit else rows
    except Exception:
        return []


def as_float(value):
    try:
        if value in [None, "", "N/A"]:
            return None
        return float(value)
    except Exception:
        return None


def fmt_float(value, decimals=1):
    value = as_float(value)
    return "N/A" if value is None else f"{value:.{decimals}f}"


def fmt_money_eur(value):
    value = as_float(value)
    return "N/A" if value is None else f"{value:,.0f} €"


def fmt_price(value):
    value = as_float(value)
    return "N/A" if value is None else f"{value:,.2f}"


def fmt_pct(value, decimals=1, signed=True):
    value = as_float(value)
    if value is None:
        return "N/A"
    prefix = "+" if signed else ""
    return f"{value:{prefix}.{decimals}f}%"


def fmt_musd(value):
    value = as_float(value)
    return "N/A" if value is None else f"{value:+.1f} M$"


def score_class(score):
    score = as_float(score)
    if score is None:
        return "neutral"
    if score >= 70:
        return "hot"
    if score >= 50:
        return "watch"
    return "quiet"


def compact_reason_list(reasons, max_items=2):
    if not reasons:
        return "Sin señales destacadas"
    return "; ".join(str(x) for x in reasons[:max_items])


PREMIUM_DASHBOARDS = [
    ("Motor de decision y rendimiento", "performance_dashboard.html", "Señales normalizadas, decisión agregada y tracking de rendimiento", "decision_engine_snapshot.json"),
    ("SEC e insiders", "sec_filing_dashboard.html", "Insiders, 8-K, 10-Q, 10-K, 13D/G y 13F", "sec_filing_snapshot.json"),
    ("Regimen macro", "macro_regime_dashboard.html", "Risk-on, risk-off, defensivos y liquidez", "macro_regime_snapshot.json"),
    ("Rotacion sectorial", "sector_rotation_dashboard.html", "Ranking de sectores, ETFs y fuerza relativa", "sector_rotation_snapshot.json"),
    ("Liquidez DeFi", "defi_liquidity_dashboard.html", "TVL y liquidez crypto por cadenas", "defi_liquidity_snapshot.json"),
    ("Catalizadores de resultados", "earnings_catalyst_dashboard.html", "Vigilancia pre/post resultados", "earnings_catalyst_snapshot.json"),
    ("Posicionamiento CFTC", "cftc_positioning_dashboard.html", "Commitment of Traders semanal", "cftc_positioning_snapshot.json"),
    ("Volumen inusual", "unusual_volume_dashboard.html", "Volumen anormal y rupturas tecnicas", "unusual_volume_snapshot.json"),
    ("Fundamentales altcoin", "altcoin_fundamentals_dashboard.html", "Fundamentales publicos de altcoins", "altcoin_fundamentals_snapshot.json"),
    ("Intradia salida mismo dia", "intraday_cashout_dashboard.html", "Ideas para entrada por la manana y salida antes del cierre", "intraday_cashout_snapshot.json"),
]


def clean_label(value):
    value = str(value or "").replace("_", " ").strip()
    return value[:1].upper() + value[1:] if value else "N/A"


def metric_value(value):
    if isinstance(value, bool):
        return "si" if value else "no"
    if isinstance(value, (int, float)):
        return fmt_float(value, 2)
    if isinstance(value, dict):
        return ", ".join(f"{clean_label(k)}: {metric_value(v)}" for k, v in list(value.items())[:6])
    if isinstance(value, list):
        return ", ".join(str(x) for x in value[:5])
    return "N/A" if value in [None, ""] else str(value)


def friendly_text(value):
    text = str(value or "")
    replacements = {
        "rotation watch": "rotacion sectorial",
        "fundamentals watch": "vigilancia fundamental",
        "unusual volume": "volumen inusual",
        "earnings setup": "vigilancia de resultados",
        "CFTC positioning watch": "posicionamiento CFTC",
        "Macro regime": "Regimen macro",
        "filing": "presentacion SEC",
        "SEC form": "formulario SEC",
        "filed": "presentado",
        "insider transaction filing": "operacion declarada por insider",
        "price reacting recently": "precio reaccionando recientemente",
        "is showing relative strength/weakness vs SPY. Monitor rotation persistence.": "muestra fuerza o debilidad relativa frente a SPY. Vigilar si la rotacion persiste.",
        "shows public market/fundamental metrics to monitor. Memecoin-style signals are excluded.": "muestra metricas publicas de mercado y fundamentales a vigilar. Se excluyen senales tipo memecoin.",
        "has abnormal volume or technical movement to monitor.": "presenta volumen anormal o movimiento tecnico a vigilar.",
        "positioning report should be reviewed for extremes and weekly changes.": "conviene revisar el posicionamiento para extremos y cambios semanales.",
        "Current proxy basket points to": "La cesta de proxies apunta a",
        "Watch confirmation across credit, duration and dollar proxies.": "Vigilar confirmacion en credito, duracion y dolar.",
        "relative vs SPY": "relativo vs SPY",
        "TVL unavailable": "TVL no disponible",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    return text


def compact_metrics(metrics, max_items=6):
    if not isinstance(metrics, dict):
        return "Sin metricas disponibles"
    items = []
    preferred = [
        "price", "rsi", "perf_5d", "perf_20d", "perf_60d", "volume_ratio",
        "tvl", "change_1d", "change_7d", "market_cap", "volume", "regime",
        "filing_date", "form", "earnings_date", "days_until",
    ]
    for key in preferred:
        if key in metrics and metrics.get(key) not in [None, "", {}]:
            items.append(f"{clean_label(key)}: {metric_value(metrics.get(key))}")
    if len(items) < max_items:
        for key, value in metrics.items():
            if key in preferred or value in [None, "", {}]:
                continue
            items.append(f"{clean_label(key)}: {metric_value(value)}")
            if len(items) >= max_items:
                break
    return "; ".join(items[:max_items]) if items else "Sin metricas disponibles"


def detail_block(summary, reasons=None, metrics=None, source=None):
    reason_text = friendly_text(compact_reason_list(reasons or [], 5))
    metric_text = compact_metrics(metrics or {}, 8)
    source_html = f'<a href="{esc(source)}">Abrir fuente</a>' if source else "Sin fuente directa"
    return f"""<details class="details">
      <summary>Ver tesis, métricas y fuente</summary>
      <div class="detail-grid">
        <div><strong>Lectura</strong><p>{esc(friendly_text(summary or 'Sin lectura disponible'))}</p></div>
        <div><strong>Motivos</strong><p>{esc(reason_text)}</p></div>
        <div><strong>Métricas</strong><p>{esc(metric_text)}</p></div>
        <div><strong>Fuente</strong><p>{source_html}</p></div>
      </div>
    </details>"""


def opportunity_record(source, asset, title, score, summary, href, reasons=None, metrics=None, source_url=None):
    score = as_float(score)
    if score is None:
        return None
    return {
        "source": source,
        "asset": asset or "N/A",
        "title": friendly_text(title or "Oportunidad a monitorizar"),
        "score": score,
        "summary": friendly_text(summary or "Sin lectura disponible."),
        "href": href,
        "reasons": reasons or [],
        "metrics": metrics or {},
        "source_url": source_url,
    }


def collect_opportunities(min_score=75):
    records = []
    state = read_json("state.json", {})
    btc = state.get("last_snapshot", {}).get("btc", {})
    rec = opportunity_record(
        "BTC",
        "BTC",
        btc.get("status", "Señal BTC"),
        btc.get("score"),
        f"Precio {fmt_money_eur(btc.get('price'))}, RSI {fmt_float(btc.get('rsi'), 1)} y régimen {btc.get('regime', 'N/A')}.",
        "dashboard.html",
        ["Señal principal BTC", f"Régimen {btc.get('regime', 'N/A')}"],
        btc,
    )
    if rec:
        records.append(rec)

    for item in state.get("last_snapshot", {}).get("stocks", {}).get("top", []):
        rec = opportunity_record(
            "Bolsa / ETFs",
            item.get("symbol"),
            f"{item.get('symbol')} oportunidad técnica",
            item.get("score"),
            f"Precio {fmt_price(item.get('price'))}, RSI {fmt_float(item.get('rsi'), 1)}, distancia a SMA200 {fmt_pct(item.get('dist200'))}.",
            "dashboard.html",
            item.get("reasons", []),
            item,
        )
        if rec:
            records.append(rec)

    for item in read_json("event_rumor_snapshot.json", []):
        rec = opportunity_record(
            "Rumores y eventos",
            item.get("ticker"),
            item.get("event_name") or item.get("opportunity_type"),
            item.get("score"),
            item.get("summary"),
            "event_rumor_dashboard.html",
            item.get("score_reasons", []) + item.get("rumors", []),
            item.get("market", {}),
            (item.get("articles") or [{}])[0].get("url"),
        )
        if rec:
            records.append(rec)

    for label, href, _description, snapshot_path in PREMIUM_DASHBOARDS:
        for item in read_json(snapshot_path, []):
            rec = opportunity_record(
                label,
                item.get("asset"),
                item.get("title"),
                item.get("score"),
                item.get("summary") or item.get("ai_brief"),
                href,
                item.get("reasons", []) + item.get("ai_watch_items", []),
                item.get("metrics", {}),
                item.get("source"),
            )
            if rec:
                records.append(rec)

    return sorted([x for x in records if x["score"] >= min_score], key=lambda x: x["score"], reverse=True)


def render_opportunities_dashboard(output_path="docs/opportunities.html", min_score=75):
    opportunities = collect_opportunities(min_score=min_score)
    rows = "".join(
        f"""<tr>
          <td><div class="company">{esc(item['asset'])}</div><div class="muted">{esc(item['source'])}</div></td>
          <td><span class="pill {score_class(item['score'])}">{fmt_float(item['score'], 0)}/100</span></td>
          <td>{esc(item['title'])}<div class="reason">{esc(item['summary'])}</div>{detail_block(item['summary'], item['reasons'], item['metrics'], item['source_url'])}</td>
          <td><a class="btn compact" href="{esc(item['href'])}">Ver detalle</a></td>
        </tr>"""
        for item in opportunities
    )
    body = f"""<div class="shell">
  <div class="topbar">
    <div>
      <h1>Oportunidades Claras</h1>
      <div class="muted">Vista filtrada con las ideas de mayor convicción del sistema. Umbral: score ≥ {min_score}.</div>
    </div>
    <nav class="nav">
      <a class="btn" href="index.html">Resumen</a>
      <a class="btn" href="performance_dashboard.html">Rendimiento</a>
      <a class="btn" href="dashboard.html">BTC</a>
      <a class="btn" href="intraday_cashout_dashboard.html">Intradia</a>
      <a class="btn" href="event_rumor_dashboard.html">Rumores</a>
      <a class="btn" href="https://github.com/DiegoSR-git/market-signal-agent/actions">Actions</a>
    </nav>
  </div>
  <section class="grid">
    <div class="card span-4"><h3>Oportunidades claras</h3><div class="metric">{len(opportunities)}</div><div class="submetric">score ≥ {min_score}, ordenadas por prioridad</div></div>
    <div class="card span-4"><h3>Mayor score</h3><div class="metric">{fmt_float(opportunities[0]['score'], 0) if opportunities else 'N/A'}</div><div class="submetric">{esc(opportunities[0]['asset']) if opportunities else 'Sin candidatas'}</div></div>
    <div class="card span-4"><h3>Actualizado</h3><div class="metric small">{utc_now_label()}</div><div class="submetric">UTC</div></div>
    <div class="card span-12">
      <h2>Ideas Prioritarias Para Revisar</h2>
      <p class="intro">Esta pantalla no ejecuta operaciones ni sustituye tu criterio. Reduce ruido y agrupa las señales con mejor puntuación para que puedas revisar la tesis, las métricas y la fuente antes de decidir.</p>
      <div class="table-wrap"><table><thead><tr><th>Activo</th><th>Score</th><th>Tesis</th><th>Detalle</th></tr></thead><tbody>{rows or '<tr><td colspan="4">No hay oportunidades con score alto ahora mismo.</td></tr>'}</tbody></table></div>
    </div>
  </section>
  <footer>Generado: {utc_now_label()}. Investigación automatizada con datos públicos; no es asesoramiento financiero personalizado.</footer>
</div>"""
    Path(output_path).write_text(render_page("Oportunidades Claras", body), encoding="utf-8")


def render_premium_snapshot_dashboard(label, snapshot_path, output_path, description):
    events = sorted(read_json(snapshot_path, []), key=lambda x: as_float(x.get("score")) or 0, reverse=True)
    high = len([x for x in events if (as_float(x.get("score")) or 0) >= 80])
    medium = len([x for x in events if 65 <= (as_float(x.get("score")) or 0) < 80])
    brief = next((x.get("ai_brief") for x in events if x.get("ai_brief")), None)
    rows = "".join(
        f"""<tr>
          <td><div class="company">{esc(item.get('asset'))}</div><div class="muted">{esc(friendly_text(item.get('title')))}</div></td>
          <td><span class="pill {score_class(item.get('score'))}">{fmt_float(item.get('score'), 0)}/100</span></td>
          <td>{esc(item.get('level', 'N/A'))}</td>
          <td>{esc(friendly_text(item.get('summary') or item.get('ai_brief') or 'Sin lectura disponible'))}<div class="reason">{esc(friendly_text(compact_reason_list(item.get('reasons', []), 4)))}</div>{detail_block(item.get('summary') or item.get('ai_brief'), item.get('reasons', []) + item.get('ai_watch_items', []), item.get('metrics', {}), item.get('source'))}</td>
        </tr>"""
        for item in events[:80]
    )
    ai_html = ""
    if brief:
        watch = "; ".join((events[0].get("ai_watch_items") or [])[:4]) if events else ""
        risks = "; ".join((events[0].get("ai_risk_notes") or [])[:3]) if events else ""
        ai_html = f"""<div class="card span-12">
      <h2>Resumen IA</h2>
      <p>{esc(friendly_text(brief))}</p>
      <div class="submetric">Vigilar: {esc(friendly_text(watch or 'N/A'))}</div>
      <div class="submetric">Riesgos: {esc(friendly_text(risks or 'N/A'))}</div>
    </div>"""
    body = f"""<div class="shell">
  <div class="topbar">
    <div>
      <h1>{esc(label)}</h1>
      <div class="muted">{esc(description)}. Datos públicos, lectura automatizada y revisión humana recomendada.</div>
    </div>
    <nav class="nav">
      <a class="btn primary" href="opportunities.html">Oportunidades Claras</a>
      <a class="btn" href="performance_dashboard.html">Rendimiento</a>
      <a class="btn" href="index.html">Resumen</a>
      <a class="btn" href="https://github.com/DiegoSR-git/market-signal-agent/actions">Actions</a>
    </nav>
  </div>
  <section class="grid">
    <div class="card span-3"><h3>Eventos</h3><div class="metric">{len(events)}</div><div class="submetric">lecturas disponibles</div></div>
    <div class="card span-3"><h3>Alto</h3><div class="metric">{high}</div><div class="submetric">score >= 80</div></div>
    <div class="card span-3"><h3>Medio</h3><div class="metric">{medium}</div><div class="submetric">score 65-79</div></div>
    <div class="card span-3"><h3>Actualizado</h3><div class="metric small">{utc_now_label()}</div><div class="submetric">UTC</div></div>
{ai_html}
    <div class="card span-12">
      <h2>Detalle Del Agente</h2>
      <p class="intro">Cada fila incluye una lectura breve y un bloque desplegable con motivos, métricas y fuente. El objetivo es ayudarte a decidir qué merece investigación adicional.</p>
      <div class="table-wrap"><table><thead><tr><th>Activo</th><th>Score</th><th>Nivel</th><th>Detalle</th></tr></thead><tbody>{rows or '<tr><td colspan="4">Sin datos disponibles todavia.</td></tr>'}</tbody></table></div>
    </div>
  </section>
  <footer>Generado: {utc_now_label()}. Investigación automatizada con datos públicos; no es asesoramiento financiero personalizado.</footer>
</div>"""
    Path(output_path).write_text(render_page(label, body), encoding="utf-8")


def render_all_premium_dashboards():
    for label, href, description, snapshot_path in PREMIUM_DASHBOARDS:
        render_premium_snapshot_dashboard(label, snapshot_path, Path("docs") / href, description)


def render_page(title, body):
    return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(title)}</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #080b10;
      --panel: #101720;
      --panel-2: #0d131b;
      --panel-3: #151f2a;
      --line: #263545;
      --text: #eef4fb;
      --muted: #9eacbb;
      --green: #42d392;
      --yellow: #f4c95d;
      --red: #ff6f61;
      --blue: #69b7ff;
      --cyan: #57d6d1;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: radial-gradient(circle at top left, rgba(87, 214, 209, .08), transparent 34rem), var(--bg);
      color: var(--text);
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.45;
    }}
    a {{ color: var(--blue); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .shell {{ width: min(1440px, calc(100% - 40px)); margin: 0 auto; padding: 28px 0 44px; }}
    .topbar {{ display: flex; justify-content: space-between; gap: 18px; align-items: flex-start; margin-bottom: 24px; padding-bottom: 18px; border-bottom: 1px solid var(--line); }}
    h1 {{ margin: 0; font-size: clamp(30px, 4vw, 54px); letter-spacing: 0; line-height: 1.02; }}
    h2 {{ margin: 0 0 12px; font-size: 18px; }}
    h3 {{ margin: 0; font-size: 15px; color: var(--muted); font-weight: 650; }}
    .muted {{ color: var(--muted); }}
    .nav {{ display: flex; gap: 10px; flex-wrap: wrap; justify-content: flex-end; }}
    .btn {{ border: 1px solid var(--line); background: #172231; color: var(--text); padding: 9px 12px; border-radius: 8px; font-weight: 750; display: inline-flex; align-items: center; justify-content: center; min-height: 38px; }}
    .btn.primary {{ border-color: rgba(66, 211, 146, .45); background: rgba(66, 211, 146, .12); color: var(--green); }}
    .btn.compact {{ min-height: 32px; padding: 6px 9px; font-size: 12px; }}
    .grid {{ display: grid; grid-template-columns: repeat(12, 1fr); gap: 14px; }}
    .card {{ background: linear-gradient(180deg, rgba(255,255,255,.025), transparent), var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 16px; min-width: 0; box-shadow: 0 14px 30px rgba(0,0,0,.18); }}
    .span-3 {{ grid-column: span 3; }}
    .span-4 {{ grid-column: span 4; }}
    .span-5 {{ grid-column: span 5; }}
    .span-7 {{ grid-column: span 7; }}
    .span-8 {{ grid-column: span 8; }}
    .span-12 {{ grid-column: span 12; }}
    .metric {{ font-size: 34px; line-height: 1.05; font-weight: 800; margin: 8px 0 4px; }}
    .metric.small {{ font-size: 20px; }}
    .submetric {{ color: var(--muted); font-size: 13px; }}
    .intro {{ color: var(--muted); max-width: 920px; margin: 0 0 14px; }}
    .pill {{ display: inline-flex; align-items: center; border: 1px solid var(--line); border-radius: 999px; padding: 4px 9px; font-size: 12px; font-weight: 800; color: var(--muted); }}
    .pill.hot {{ color: var(--green); border-color: rgba(61, 220, 151, .35); background: rgba(61, 220, 151, .08); }}
    .pill.watch {{ color: var(--yellow); border-color: rgba(247, 201, 72, .35); background: rgba(247, 201, 72, .08); }}
    .pill.quiet {{ color: var(--muted); }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ padding: 10px 8px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }}
    th {{ color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .04em; }}
    td {{ font-size: 14px; }}
    tr:last-child td {{ border-bottom: 0; }}
    .table-wrap {{ overflow-x: auto; }}
    .company {{ font-weight: 800; }}
    .reason {{ color: var(--muted); font-size: 12px; margin-top: 3px; max-width: 520px; }}
    .details {{ margin-top: 8px; color: var(--muted); }}
    .details summary {{ cursor: pointer; color: var(--blue); font-weight: 750; font-size: 12px; }}
    .detail-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin-top: 10px; padding: 12px; background: var(--panel-2); border: 1px solid var(--line); border-radius: 8px; }}
    .detail-grid strong {{ color: var(--text); display: block; margin-bottom: 4px; font-size: 12px; text-transform: uppercase; }}
    .detail-grid p {{ margin: 0; font-size: 13px; }}
    .status-line {{ display: flex; align-items: center; justify-content: space-between; gap: 12px; }}
    .bar {{ height: 8px; background: #1a2430; border-radius: 999px; overflow: hidden; margin-top: 10px; }}
    .bar > span {{ display: block; height: 100%; background: var(--green); width: var(--w); }}
    footer {{ color: var(--muted); font-size: 12px; margin-top: 20px; }}
    @media (max-width: 980px) {{
      .span-3, .span-4, .span-5, .span-7, .span-8 {{ grid-column: span 12; }}
      .topbar {{ display: block; }}
      .nav {{ justify-content: flex-start; margin-top: 16px; }}
      .detail-grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
{body}
</body>
</html>"""


def render_home_dashboard(
    output_path,
    state_path="state.json",
    signal_log_path="signals_log.csv",
    event_snapshot_path="event_rumor_snapshot.json",
    event_log_path="event_rumor_log.csv",
):
    state = read_json(state_path, {})
    btc = state.get("last_snapshot", {}).get("btc", {})
    stocks = state.get("last_snapshot", {}).get("stocks", {})
    orders = state.get("orders", {})
    events = read_json(event_snapshot_path, [])
    event_log = read_csv_rows(event_log_path, limit=1)
    signal_rows = list(reversed(read_csv_rows(signal_log_path, limit=8)))

    btc_score = btc.get("score")
    btc_updated = btc.get("time_utc") or state.get("last_run_utc") or "N/A"
    event_updated = event_log[-1]["time_utc"] if event_log else "N/A"
    top_events = sorted(events, key=lambda x: as_float(x.get("score")) or 0, reverse=True)[:12]
    hot_count = len([x for x in events if (as_float(x.get("score")) or 0) >= 50])
    touched_orders = len([x for x in orders.values() if x.get("first_triggered_utc")])
    clear_opportunities = collect_opportunities(min_score=75)

    event_rows = "".join(
        f"""<tr>
          <td><div class="company">{esc(item.get('ticker'))}</div><div class="muted">{esc(item.get('company'))}</div></td>
          <td><span class="pill {score_class(item.get('score'))}">{esc(item.get('score'))}/100</span></td>
          <td>{esc(item.get('event_name') or 'N/A')}<div class="reason">{esc(compact_reason_list(item.get('score_reasons', []), 3))}</div></td>
          <td>{fmt_price(item.get('market', {}).get('price'))}</td>
          <td>{fmt_float(item.get('market', {}).get('rsi'), 1)}</td>
          <td>{fmt_pct(item.get('market', {}).get('perf_20d'))}</td>
        </tr>"""
        for item in top_events
    )

    order_rows = "".join(
        f"""<tr>
          <td>{esc(order_id)}<div class="muted">{esc(rec.get('name'))}</div></td>
          <td>{fmt_money_eur(rec.get('price_eur'))}</td>
          <td>{fmt_money_eur(rec.get('amount_eur'))}</td>
          <td><span class="pill {'hot' if rec.get('first_triggered_utc') else 'quiet'}">{'Tocada' if rec.get('first_triggered_utc') else 'Pendiente'}</span></td>
          <td>{esc(rec.get('times_seen', 0))}</td>
        </tr>"""
        for order_id, rec in sorted(orders.items(), key=lambda x: x[1].get("price_eur", 0), reverse=True)
    )

    signal_rows_html = "".join(
        f"""<tr>
          <td>{esc(row.get('time_utc'))}</td>
          <td>{esc(row.get('asset'))}</td>
          <td>{esc(row.get('signal_type'))}</td>
          <td>{esc(row.get('score'))}</td>
          <td>{fmt_money_eur(row.get('price'))}</td>
          <td>{esc(row.get('status'))}</td>
        </tr>"""
        for row in signal_rows
    )
    premium_links = "".join(
        f"""<tr>
          <td><a href="{esc(href)}">{esc(label)}</a></td>
          <td>{esc(description)}</td>
        </tr>"""
        for label, href, description, _snapshot in PREMIUM_DASHBOARDS
    )

    body = f"""<div class="shell">
  <div class="topbar">
    <div>
      <h1>Market Signal Agent</h1>
      <div class="muted">Panel publicado en GitHub Pages con los últimos datos persistidos por los workflows.</div>
    </div>
    <nav class="nav">
      <a class="btn primary" href="opportunities.html">Oportunidades Claras</a>
      <a class="btn" href="performance_dashboard.html">Rendimiento</a>
      <a class="btn" href="intraday_cashout_dashboard.html">Intradia</a>
      <a class="btn" href="dashboard.html">BTC</a>
      <a class="btn" href="event_rumor_dashboard.html">Event Rumor</a>
      <a class="btn" href="macro_regime_dashboard.html">Research Premium</a>
      <a class="btn" href="https://github.com/DiegoSR-git/market-signal-agent">GitHub</a>
    </nav>
  </div>

  <section class="grid">
    <div class="card span-3">
      <h3>BTC Signal</h3>
      <div class="status-line"><div class="metric">{esc(btc_score or 'N/A')}/100</div><span class="pill {score_class(btc_score)}">{esc(btc.get('status', 'N/A'))}</span></div>
      <div class="bar" style="--w:{max(0, min(100, int(as_float(btc_score) or 0)))}%"><span></span></div>
      <div class="submetric">Precio {fmt_money_eur(btc.get('price'))} · RSI {fmt_float(btc.get('rsi'), 1)} · Régimen {esc(btc.get('regime', 'N/A'))}</div>
    </div>
    <div class="card span-3">
      <h3>Oportunidades Claras</h3>
      <div class="metric">{len(clear_opportunities)}</div>
      <div class="submetric">score ≥ 75 · <a href="opportunities.html">ver selección prioritaria</a></div>
    </div>
    <div class="card span-3">
      <h3>Radar De Rumores</h3>
      <div class="metric">{len(events)}</div>
      <div class="submetric">{hot_count} candidatas con score ≥ 50 · última actualización {esc(event_updated)}</div>
    </div>
    <div class="card span-3">
      <h3>Gestión</h3>
      <div class="metric">{touched_orders}/{len(orders)}</div>
      <div class="submetric">órdenes BTC tocadas · oportunidades stock {esc(stocks.get('opportunities', 0))}</div>
    </div>

    <div class="card span-7">
      <h2>Oportunidades Por Noticias Y Rumores</h2>
      <div class="table-wrap"><table><thead><tr><th>Empresa</th><th>Score</th><th>Catalizador</th><th>Precio</th><th>RSI</th><th>20D</th></tr></thead><tbody>{event_rows or '<tr><td colspan="6">Sin datos de event rumor todavía</td></tr>'}</tbody></table></div>
    </div>
    <div class="card span-5">
      <h2>BTC Snapshot</h2>
      <table><tbody>
        <tr><td>Actualizado</td><td>{esc(btc_updated)}</td></tr>
        <tr><td>SMA200</td><td>{fmt_money_eur(btc.get('sma200'))}</td></tr>
        <tr><td>Fear & Greed</td><td>{esc(btc.get('fear', 'N/A'))}</td></tr>
        <tr><td>ETF total</td><td>{fmt_musd(btc.get('etf_total'))}</td></tr>
        <tr><td>IBIT</td><td>{fmt_musd(btc.get('ibit'))}</td></tr>
        <tr><td>Open Interest 24h</td><td>{fmt_pct(btc.get('oi_24h'))}</td></tr>
      </tbody></table>
    </div>

    <div class="card span-7">
      <h2>Órdenes BTC</h2>
      <div class="table-wrap"><table><thead><tr><th>Orden</th><th>Precio</th><th>Importe</th><th>Estado</th><th>Veces</th></tr></thead><tbody>{order_rows or '<tr><td colspan="5">Sin órdenes configuradas</td></tr>'}</tbody></table></div>
    </div>
    <div class="card span-5">
      <h2>Últimas Señales BTC</h2>
      <div class="table-wrap"><table><thead><tr><th>Hora</th><th>Activo</th><th>Tipo</th><th>Score</th><th>Precio</th><th>Estado</th></tr></thead><tbody>{signal_rows_html or '<tr><td colspan="6">Sin señales registradas</td></tr>'}</tbody></table></div>
    </div>
    <div class="card span-12">
      <h2>Agentes Premium De Investigacion</h2>
      <p class="intro">Cada panel resume una fuente de ventaja distinta: filings, regimen macro, rotacion, liquidez crypto, volumen y catalizadores. Usa la página de oportunidades claras para filtrar ruido y esta tabla para investigar el detalle por módulo.</p>
      <div class="table-wrap"><table><thead><tr><th>Panel</th><th>Cobertura</th></tr></thead><tbody>{premium_links}</tbody></table></div>
    </div>
  </section>
  <footer>Generado: {utc_now_label()}. Datos procedentes de <code>state.json</code>, <code>signals_log.csv</code>, <code>event_rumor_snapshot.json</code> y <code>event_rumor_log.csv</code>.</footer>
</div>"""

    Path(output_path).write_text(render_page("Panel Market Signal Agent", body), encoding="utf-8")
    render_opportunities_dashboard(Path(output_path).with_name("opportunities.html"))


def render_event_dashboard(results, output_path):
    rows = []
    for item in sorted(results, key=lambda x: as_float(x.get("score")) or 0, reverse=True):
        market = item.get("market", {})
        rumors = "; ".join(item.get("rumors", [])[:3]) or compact_reason_list(item.get("score_reasons", []), 3)
        articles = item.get("articles", [])
        first_url = articles[0].get("url") if articles else None
        source_link = f'<a href="{esc(first_url)}">fuente</a>' if first_url else "N/A"
        details = detail_block(
            item.get("summary"),
            item.get("score_reasons", []) + item.get("rumors", []),
            market,
            first_url,
        )
        rows.append(f"""<tr>
          <td><div class="company">{esc(item.get('ticker'))}</div><div class="muted">{esc(item.get('company'))}</div></td>
          <td><span class="pill {score_class(item.get('score'))}">{esc(item.get('score'))}/100</span></td>
          <td>{esc(item.get('opportunity_type', 'none'))}</td>
          <td>{esc(item.get('event_name') or 'N/A')}<div class="reason">{esc(rumors)}</div>{details}</td>
          <td>{fmt_price(market.get('price'))}</td>
          <td>{fmt_float(market.get('rsi'), 1)}</td>
          <td>{fmt_pct(market.get('perf_20d'))}</td>
          <td>{source_link}</td>
        </tr>""")

    body = f"""<div class="shell">
  <div class="topbar">
    <div>
      <h1>Radar De Rumores Y Eventos</h1>
      <div class="muted">Oportunidades públicas por noticias, rumores, eventos corporativos y momentum.</div>
    </div>
    <nav class="nav">
      <a class="btn primary" href="opportunities.html">Oportunidades Claras</a>
      <a class="btn" href="performance_dashboard.html">Rendimiento</a>
      <a class="btn" href="index.html">Resumen</a>
      <a class="btn" href="dashboard.html">BTC</a>
      <a class="btn" href="https://github.com/DiegoSR-git/market-signal-agent/actions">Actions</a>
    </nav>
  </div>
  <section class="grid">
    <div class="card span-3"><h3>Empresas Analizadas</h3><div class="metric">{len(results)}</div><div class="submetric">ordenadas por score</div></div>
    <div class="card span-3"><h3>Score ≥ 50</h3><div class="metric">{len([x for x in results if (as_float(x.get('score')) or 0) >= 50])}</div><div class="submetric">candidatas calientes</div></div>
    <div class="card span-3"><h3>Score Medio</h3><div class="metric">{fmt_float(sum((as_float(x.get('score')) or 0) for x in results) / len(results) if results else None, 1)}</div><div class="submetric">sobre 100</div></div>
    <div class="card span-3"><h3>Actualizado</h3><div class="metric" style="font-size:20px">{utc_now_label()}</div><div class="submetric">UTC</div></div>
    <div class="card span-12">
      <h2>Ranking De Catalizadores</h2>
      <p class="intro">Lectura de mercado basada en noticias públicas, eventos corporativos y contexto técnico. Abre el detalle de cada fila para revisar tesis, motivos, métricas y fuente antes de actuar.</p>
      <div class="table-wrap"><table><thead><tr><th>Empresa</th><th>Score</th><th>Tipo</th><th>Catalizador</th><th>Precio</th><th>RSI</th><th>20D</th><th>Fuente</th></tr></thead><tbody>{''.join(rows) if rows else '<tr><td colspan="8">Sin datos</td></tr>'}</tbody></table></div>
    </div>
  </section>
  <footer>Generado: {utc_now_label()}. Solo información pública; no ejecuta operaciones.</footer>
</div>"""
    Path(output_path).write_text(render_page("Radar De Rumores Y Eventos", body), encoding="utf-8")
