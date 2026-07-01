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
      --bg: #090d14;
      --panel: #111821;
      --panel-2: #0d131b;
      --line: #263241;
      --text: #e7edf5;
      --muted: #9aa7b7;
      --green: #3ddc97;
      --yellow: #f7c948;
      --red: #ff6b6b;
      --blue: #5aa9ff;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.45;
    }}
    a {{ color: var(--blue); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .shell {{ width: min(1420px, calc(100% - 40px)); margin: 0 auto; padding: 28px 0 44px; }}
    .topbar {{ display: flex; justify-content: space-between; gap: 18px; align-items: flex-start; margin-bottom: 24px; }}
    h1 {{ margin: 0; font-size: clamp(30px, 4vw, 54px); letter-spacing: 0; line-height: 1.02; }}
    h2 {{ margin: 0 0 12px; font-size: 18px; }}
    h3 {{ margin: 0; font-size: 15px; color: var(--muted); font-weight: 650; }}
    .muted {{ color: var(--muted); }}
    .nav {{ display: flex; gap: 10px; flex-wrap: wrap; justify-content: flex-end; }}
    .btn {{ border: 1px solid var(--line); background: #18212c; color: var(--text); padding: 9px 12px; border-radius: 8px; font-weight: 700; }}
    .grid {{ display: grid; grid-template-columns: repeat(12, 1fr); gap: 14px; }}
    .card {{ background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 16px; min-width: 0; }}
    .span-3 {{ grid-column: span 3; }}
    .span-4 {{ grid-column: span 4; }}
    .span-5 {{ grid-column: span 5; }}
    .span-7 {{ grid-column: span 7; }}
    .span-8 {{ grid-column: span 8; }}
    .span-12 {{ grid-column: span 12; }}
    .metric {{ font-size: 34px; line-height: 1.05; font-weight: 800; margin: 8px 0 4px; }}
    .submetric {{ color: var(--muted); font-size: 13px; }}
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
    .status-line {{ display: flex; align-items: center; justify-content: space-between; gap: 12px; }}
    .bar {{ height: 8px; background: #1a2430; border-radius: 999px; overflow: hidden; margin-top: 10px; }}
    .bar > span {{ display: block; height: 100%; background: var(--green); width: var(--w); }}
    footer {{ color: var(--muted); font-size: 12px; margin-top: 20px; }}
    @media (max-width: 980px) {{
      .span-3, .span-4, .span-5, .span-7, .span-8 {{ grid-column: span 12; }}
      .topbar {{ display: block; }}
      .nav {{ justify-content: flex-start; margin-top: 16px; }}
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

    body = f"""<div class="shell">
  <div class="topbar">
    <div>
      <h1>Market Signal Agent</h1>
      <div class="muted">Dashboard publicado en GitHub Pages con los últimos datos persistidos por los workflows.</div>
    </div>
    <nav class="nav">
      <a class="btn" href="dashboard.html">BTC</a>
      <a class="btn" href="event_rumor_dashboard.html">Event Rumor</a>
      <a class="btn" href="https://github.com/DiegoSR-git/market-signal-agent">GitHub</a>
    </nav>
  </div>

  <section class="grid">
    <div class="card span-4">
      <h3>BTC Signal</h3>
      <div class="status-line"><div class="metric">{esc(btc_score or 'N/A')}/100</div><span class="pill {score_class(btc_score)}">{esc(btc.get('status', 'N/A'))}</span></div>
      <div class="bar" style="--w:{max(0, min(100, int(as_float(btc_score) or 0)))}%"><span></span></div>
      <div class="submetric">Precio {fmt_money_eur(btc.get('price'))} · RSI {fmt_float(btc.get('rsi'), 1)} · Régimen {esc(btc.get('regime', 'N/A'))}</div>
    </div>
    <div class="card span-4">
      <h3>Event Rumor Watch</h3>
      <div class="metric">{len(events)}</div>
      <div class="submetric">{hot_count} candidatas con score ≥ 50 · última actualización {esc(event_updated)}</div>
    </div>
    <div class="card span-4">
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
  </section>
  <footer>Generado: {utc_now_label()}. Datos procedentes de <code>state.json</code>, <code>signals_log.csv</code>, <code>event_rumor_snapshot.json</code> y <code>event_rumor_log.csv</code>.</footer>
</div>"""

    Path(output_path).write_text(render_page("Market Signal Agent Dashboard", body), encoding="utf-8")


def render_event_dashboard(results, output_path):
    rows = []
    for item in sorted(results, key=lambda x: as_float(x.get("score")) or 0, reverse=True):
        market = item.get("market", {})
        rumors = "; ".join(item.get("rumors", [])[:3]) or compact_reason_list(item.get("score_reasons", []), 3)
        articles = item.get("articles", [])
        first_url = articles[0].get("url") if articles else None
        source_link = f'<a href="{esc(first_url)}">fuente</a>' if first_url else "N/A"
        rows.append(f"""<tr>
          <td><div class="company">{esc(item.get('ticker'))}</div><div class="muted">{esc(item.get('company'))}</div></td>
          <td><span class="pill {score_class(item.get('score'))}">{esc(item.get('score'))}/100</span></td>
          <td>{esc(item.get('opportunity_type', 'none'))}</td>
          <td>{esc(item.get('event_name') or 'N/A')}<div class="reason">{esc(rumors)}</div></td>
          <td>{fmt_price(market.get('price'))}</td>
          <td>{fmt_float(market.get('rsi'), 1)}</td>
          <td>{fmt_pct(market.get('perf_20d'))}</td>
          <td>{source_link}</td>
        </tr>""")

    body = f"""<div class="shell">
  <div class="topbar">
    <div>
      <h1>Event Rumor Watch</h1>
      <div class="muted">Oportunidades públicas por noticias, rumores, eventos corporativos y momentum.</div>
    </div>
    <nav class="nav">
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
      <div class="table-wrap"><table><thead><tr><th>Empresa</th><th>Score</th><th>Tipo</th><th>Catalizador</th><th>Precio</th><th>RSI</th><th>20D</th><th>Fuente</th></tr></thead><tbody>{''.join(rows) if rows else '<tr><td colspan="8">Sin datos</td></tr>'}</tbody></table></div>
    </div>
  </section>
  <footer>Generado: {utc_now_label()}. Solo información pública; no ejecuta operaciones.</footer>
</div>"""
    Path(output_path).write_text(render_page("Event Rumor Watch", body), encoding="utf-8")
