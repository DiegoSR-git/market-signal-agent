from __future__ import annotations

import json
from pathlib import Path

from dashboard_utils import esc, fmt_pct, fmt_price, render_page, score_class

from .config import live_signal_allowed
from .models import AlphaSnapshot
from .provider_factory import build_provider_bundle
from .providers.mock import FixtureAnalystProvider, FixtureFXProvider, FixtureMacroProvider, FixtureNewsProvider, FixtureUniverseProvider, MockMarketDataProvider
from .readiness import ProviderBundle
from .scanner import build_snapshot


def default_providers(config: dict, now=None) -> dict:
    bundle = ProviderBundle(
        market_data=MockMarketDataProvider(now=now),
        universe=FixtureUniverseProvider(),
        analysts=FixtureAnalystProvider(),
        news=FixtureNewsProvider(),
        macro=FixtureMacroProvider(),
        index_data=None,
        fx=FixtureFXProvider(),
    )
    return bundle.as_dict()


def render_text(snapshot: AlphaSnapshot) -> str:
    best = snapshot.best_operation
    lines = [
        snapshot.analysis_timestamp.isoformat(),
        "",
        f"Mercado: {snapshot.market_status.value}",
        f"Regimen: {snapshot.market_regime.regime.value}",
        f"SPY proxy: {snapshot.market_regime.spy_change_pct}",
        f"QQQ proxy: {snapshot.market_regime.qqq_change_pct}",
        f"VIX: {snapshot.market_regime.vix}",
        f"Calidad general: {'OK' if snapshot.signal_allowed else 'BLOQUEADA'}",
        f"Veredicto: {'OPERAR' if snapshot.signal_allowed else 'NO OPERAR'}",
        "",
        "MEJOR OPERACION DEL DIA",
    ]
    if not best:
        lines.append("NO OPERAR")
        lines.extend(snapshot.blocking_reasons)
    else:
        lines.extend([
            f"Accion: {best.symbol}",
            f"Motivo: {best.setup.evidence[0] if best.setup.evidence else 'setup valido'}",
            f"Condicion entrada: {best.setup.trigger}",
            f"Stop: {best.setup.stop}",
            f"Objetivo: {best.setup.target1}",
            f"Riesgo monetario: {best.risk.risk_eur if best.risk else None} EUR",
            f"B/R: {best.setup.risk_reward1}",
            f"Cancelacion: {best.setup.invalidation}",
        ])
    lines.extend(["", "ESCENARIO DE NO ENTRADA", "Datos insuficientes, stale, spread alto, fuera de ventana o setup sin confirmar."])
    return "\n".join(lines)


def candidate_row(candidate) -> str:
    score = candidate.score.total
    setup = candidate.setup
    risk = candidate.risk
    analysts = candidate.analysts
    median_upside = None
    if analysts and analysts.target_median and candidate.price:
        median_upside = ((analysts.target_median / candidate.price) - 1) * 100
    return f"""<tr>
      <td><div class="company">{esc(candidate.symbol)}</div><div class="muted">{esc(candidate.company)}</div></td>
      <td><span class="pill {score_class(score)}">{score:.0f}/100</span><div class="muted">{esc(candidate.score.risk_category.value)}</div></td>
      <td>{fmt_price(candidate.price)}<div class="reason">Bid {fmt_price(candidate.metrics.get('bid'))} / Ask {fmt_price(candidate.metrics.get('ask'))} · Spread {fmt_pct(candidate.metrics.get('spread_pct'), 3, signed=False)}</div></td>
      <td>{fmt_pct(candidate.metrics.get('rvol'), 2, signed=False)}<div class="reason">Gap {fmt_pct(candidate.metrics.get('gap_pct'))} · ATR usado {fmt_pct(candidate.metrics.get('atr_consumed_pct'), 1, signed=False)}</div></td>
      <td>{esc(analysts.analyst_count if analysts else 'N/A')}<div class="reason">Potencial mediano {fmt_pct(median_upside)}</div></td>
      <td>{esc(setup.setup_type.value)}<div class="reason">{esc(setup.status.value)} · {esc(setup.trigger)}</div></td>
      <td>{esc(setup.entry_zone)}<div class="reason">Stop {fmt_price(setup.stop)} · T1 {fmt_price(setup.target1)} · T2 {fmt_price(setup.target2)} · B/R {esc(round(setup.risk_reward1, 2) if setup.risk_reward1 else 'N/A')}</div></td>
      <td>{esc('; '.join(candidate.score.blocking_reasons or candidate.data_quality.get('blocking_reasons', []) or ['OK']))}</td>
      <td>{esc(candidate.quote.timestamp.isoformat() if candidate.quote and candidate.quote.timestamp else 'N/A')}</td>
    </tr>"""


def render_alpha_dashboard(snapshot: AlphaSnapshot, output_dir: str | Path) -> None:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    rows = "".join(candidate_row(c) for c in sorted(snapshot.candidates, key=lambda x: x.score.total, reverse=True))
    best = snapshot.best_operation
    banner = ""
    if snapshot.data_mode.value == "development":
        banner = """<div class="card span-12 danger"><h2>MODO DESARROLLO</h2><p>DATOS IEX / COBERTURA PARCIAL. NO UTILIZAR COMO SENAL REAL DE TRADING.</p></div>"""
    best_html = "<p class='intro'>MEJOR OPERACION DEL DIA: NO OPERAR</p>"
    if best:
        best_html = f"""<table><tbody>
          <tr><td>Accion</td><td>{esc(best.symbol)} - {esc(best.company)}</td></tr>
          <tr><td>Motivo</td><td>{esc(best.setup.evidence[0] if best.setup.evidence else 'setup valido')}</td></tr>
          <tr><td>Condicion entrada</td><td>{esc(best.setup.trigger)}</td></tr>
          <tr><td>Stop</td><td>{fmt_price(best.setup.stop)}</td></tr>
          <tr><td>Objetivo</td><td>{fmt_price(best.setup.target1)}</td></tr>
          <tr><td>Riesgo monetario</td><td>{fmt_price(best.risk.risk_eur if best.risk else None)} EUR</td></tr>
          <tr><td>B/R</td><td>{esc(round(best.setup.risk_reward1, 2) if best.setup.risk_reward1 else 'N/A')}</td></tr>
          <tr><td>Cancelacion</td><td>{esc(best.setup.invalidation)}</td></tr>
        </tbody></table>"""
    health_html = "".join(
        f"<tr><td>{esc(name)}</td><td><span class='pill {score_class(80 if status == 'GREEN' else 30)}'>{esc(status)}</span></td></tr>"
        for name, status in snapshot.provider_health.items()
    )
    readiness_html = "".join(
        f"<tr><td>{esc(check.name)}</td><td>{esc(check.status.value)}</td><td>{esc(check.reason)}</td></tr>"
        for check in snapshot.production_readiness.checks
    )
    body = f"""<div class="shell">
  <div class="topbar">
    <div>
      <h1>Alpha Intradia</h1>
      <div class="muted">LONG-only sobre acciones ordinarias USA large cap. Sin ordenes reales.</div>
    </div>
    <nav class="nav">
      <a class="btn primary" href="../index.html">Market Signal</a>
      <a class="btn" href="../performance_dashboard.html">Rendimiento Legacy</a>
      <a class="btn" href="https://github.com/DiegoSR-git/market-signal-agent/actions">Actions</a>
    </nav>
  </div>
  <section class="grid">
    {banner}
    <div class="card span-3"><h3>Market Status</h3><div class="metric small" data-alpha-status>{esc(snapshot.market_status.value)}</div><div class="submetric">{esc(snapshot.analysis_timestamp.isoformat())}</div></div>
    <div class="card span-3"><h3>Data Feed</h3><div class="metric small">{esc(snapshot.data_feed.upper())}</div><div class="submetric">Full coverage: false</div></div>
    <div class="card span-3"><h3>Signals Allowed</h3><div class="metric small">{'SI' if snapshot.signal_allowed else 'NO'}</div><div class="submetric">{esc('; '.join(snapshot.blocking_reasons[:2]))}</div></div>
    <div class="card span-3"><h3>Regimen</h3><div class="metric small">{esc(snapshot.market_regime.regime.value)}</div><div class="submetric">SPY {fmt_pct(snapshot.market_regime.spy_change_pct)} · QQQ {fmt_pct(snapshot.market_regime.qqq_change_pct)}</div></div>
    <div class="card span-5"><h2>DATA HEALTH</h2><div class="table-wrap"><table><tbody>{health_html}</tbody></table></div></div>
    <div class="card span-7"><h2>PRODUCTION READINESS</h2><p class="intro">Production ready: {'SI' if snapshot.production_readiness.production_ready else 'NO'} · SIGNALS ALLOWED: {'SI' if snapshot.signal_allowed else 'NO'}</p><div class="table-wrap"><table><thead><tr><th>Check</th><th>Estado</th><th>Razon</th></tr></thead><tbody>{readiness_html}</tbody></table></div></div>
    <div class="card span-12"><h2>Best Operation</h2>{best_html}</div>
    <div class="card span-12">
      <h2>Candidatas Alpha</h2>
      <p class="intro">Tabla de investigacion. Una candidata necesita datos frescos, filtros duros, setup condicional y B/R minimo para pasar.</p>
      <div class="table-wrap"><table><thead><tr><th>Ticker</th><th>Score</th><th>Precio</th><th>Volumen</th><th>Analistas</th><th>Setup</th><th>Entrada</th><th>Bloqueos</th><th>Data timestamp</th></tr></thead><tbody>{rows or '<tr><td colspan="9">Sin candidatas</td></tr>'}</tbody></table></div>
    </div>
    <div class="card span-12"><h2>No-entry Scenario</h2><p class="intro">NO OPERAR si los datos son stale, falta bid/ask/VWAP/RVOL/analistas, hay contradiccion entre proveedores, el mercado esta fuera de ventana, el spread supera el maximo o el setup no confirma.</p></div>
  </section>
  <script src="app.js"></script>
  <footer>Generado en {esc(snapshot.analysis_timestamp.isoformat())}. Alpha Intradia es informativo, no ejecuta ordenes ni constituye asesoramiento personalizado.</footer>
</div>"""
    (output / "index.html").write_text(render_page("Alpha Intradia", body), encoding="utf-8")
    (output / "snapshot.json").write_text(json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")


def run_alpha(config: dict, providers: dict | None = None, now=None) -> AlphaSnapshot:
    providers = providers or build_provider_bundle(config, now=now)
    snapshot = build_snapshot(providers, config, now=now)
    Path(config.get("output", {}).get("snapshot", "alpha_intraday_snapshot.json")).write_text(
        json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    render_alpha_dashboard(snapshot, config.get("output", {}).get("dashboard_dir", "docs/alpha"))
    return snapshot
