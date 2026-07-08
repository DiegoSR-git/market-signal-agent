# Agentes Premium De Investigacion

V1 modular de agentes de research automatizado con datos publicos, Telegram multi-chat, GitHub Models, state anti-spam, snapshots, logs CSV y dashboards en `docs/`.

No ejecutan ordenes, no usan informacion privilegiada y no generan asesoramiento financiero personalizado. El lenguaje de alertas esta orientado a vigilancia, catalizadores y riesgos.

## Agentes

| Agente | Script | Config | Panel |
| --- | --- | --- | --- |
| SEC e insiders | `sec_filing_agent.py` | `config_sec.yaml` | `docs/sec_filing_dashboard.html` |
| Regimen macro | `macro_regime_agent.py` | `config_macro.yaml` | `docs/macro_regime_dashboard.html` |
| Rotacion sectorial | `sector_rotation_agent.py` | `config_sector_rotation.yaml` | `docs/sector_rotation_dashboard.html` |
| Liquidez DeFi | `defi_liquidity_agent.py` | `config_defi.yaml` | `docs/defi_liquidity_dashboard.html` |
| Catalizadores de resultados | `earnings_catalyst_agent.py` | `config_earnings.yaml` | `docs/earnings_catalyst_dashboard.html` |
| Posicionamiento CFTC | `cftc_positioning_agent.py` | `config_cftc.yaml` | `docs/cftc_positioning_dashboard.html` |
| Volumen inusual | `unusual_volume_agent.py` | `config_unusual_volume.yaml` | `docs/unusual_volume_dashboard.html` |
| Fundamentales altcoin | `altcoin_fundamentals_agent.py` | `config_altcoins.yaml` | `docs/altcoin_fundamentals_dashboard.html` |
| Intradia salida mismo dia | `intraday_cashout_agent.py` | `config_intraday_cashout.yaml` | `docs/intraday_cashout_dashboard.html` |
| Motor de decision y rendimiento | `signal_performance_agent.py` | `config_signal_engine.yaml` | `docs/performance_dashboard.html` |

## Probar en local

```bash
python -u sec_filing_agent.py --dry-run --force
python -u macro_regime_agent.py --dry-run --force
python -u sector_rotation_agent.py --dry-run --force
python -u defi_liquidity_agent.py --dry-run --force
python -u earnings_catalyst_agent.py --dry-run --force
python -u cftc_positioning_agent.py --dry-run --force
python -u unusual_volume_agent.py --dry-run --force
python -u altcoin_fundamentals_agent.py --dry-run --force
python -u intraday_cashout_agent.py --dry-run --force
python -u signal_performance_agent.py --skip-price-fetches
```

El agente intradia cruza los snapshots ya generados por el resto de scripts, pero antes de marcar una entrada como operable valida datos pre-market en tiempo casi real: timestamp, bid/ask, spread, previous close, gap, VWAP, high/low, volumen pre-market y fuerza relativa frente a QQQ/SPY. Si faltan datos criticos queda `INVALID`; si el precio pre-market supera `max_stale_seconds` queda `STALE`.

La logica cambia por horario espanol: antes de las 15:00 solo vigila, entre 15:00 y 15:25 busca setups pre-market, de 15:25 a 15:30 evita entradas a mercado y de 15:30 a 15:35 exige confirmacion sin perseguir velas. Los setups minimos son `LONG_CONTINUATION`, `SHORT_WEAKNESS`, `GAP_FADE` y `NO_TRADE`. La configuracion incluye apalancamiento x5, riesgo por operacion, spread maximo, volumen minimo, distancia a VWAP y riesgo/beneficio minimo 1:1.5.

El motor intradia devuelve estados accionables: `READY_LONG`, `READY_SHORT`, `WAITING_CONFIRMATION`, `TOO_LATE`, `SPREAD_TOO_WIDE`, `LOW_VOLUME`, `STALE_DATA` y `NO_TRADE`. Para cuenta pequena calcula tamano teorico, margen requerido, perdida maxima diaria, coste del spread y R/R neto antes de enviar alertas.

## Motor de decision y rendimiento

`signal_performance_agent.py` cruza los resultados de todos los agentes y crea una capa comun:

- `unified_signals.json`: señales normalizadas con activo, agente, score, direccion, timestamp, validez, entrada, stop, objetivo, R/R y enlace al dashboard fuente.
- `decision_engine_snapshot.json`: decision agregada por activo (`INTRADAY_READY`, `BUY_WATCH`, `WATCHLIST`, `RISK_OFF`, `NO_TRADE_INTRADIA`, `LOW_PRIORITY`).
- `signal_performance.json`: tracking de señales frente al ultimo precio disponible para estimar retorno, TP/SL y win rate.
- `docs/performance_dashboard.html`: pantalla profesional de decision agregada y rendimiento.

El workflow `Signal Performance Engine` puede ejecutarse manualmente o por cron. El workflow `Ejecutar Todo En Cola Force` tambien lo lanza al final, despues de generar los snapshots del resto de agentes.

## Probar en GitHub Actions

En la pestana **Actions**, abre el workflow correspondiente y ejecuta **Run workflow** con:

```text
force=true
```

`force=true` envia el top de eventos aunque no alcance el umbral configurado. En modo normal solo envia Telegram si el score supera `alerts.min_score_to_alert` y respeta `cooldown_hours`.

## Secrets y variables

Secrets:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID` opcional si usas un chat unico

Variables:

- `TELEGRAM_CHAT_IDS` opcional, varios chats separados por coma
- `SEC_USER_AGENT` recomendado para SEC EDGAR, por ejemplo `market-signal-agent diego@example.com`

GitHub Models usa `GITHUB_TOKEN` del workflow con:

```yaml
permissions:
  models: read
```

## Persistencia

Cada agente genera:

- `*_state.json`: cooldown anti-spam y ultima ejecucion
- `*_snapshot.json`: ultimo ranking completo
- `*_log.csv`: historico append-only
- `docs/*_dashboard.html`: panel publicado por GitHub Pages
- `unified_signals.json`, `decision_engine_snapshot.json`, `signal_performance.json`: capa agregada de decision y rendimiento

Los workflows hacen commit automatico de estos archivos con `[skip ci]`.
