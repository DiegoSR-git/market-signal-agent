# ALPHA INTRADIA V2 - Implementation Report

## 1. Baseline encontrado

- Rama base: `origin/master`.
- Legacy principal: `agent.py`, `event_rumor_agent.py`, `premium_agent_utils.py`, `intraday_cashout_agent.py`, `signal_engine.py`.
- Telegram multi-chat existente: `TELEGRAM_CHAT_ID` + `TELEGRAM_CHAT_IDS`.
- Pages existente: `docs/index.html`, `docs/dashboard.html`, `docs/opportunities.html` y dashboards por agente.
- Workflows existentes preservados: signal, daily, weekly, healthcheck, event rumor, premium agents, intraday cashout, run-all-force y signal performance.
- Tests legacy encontrados: `tests/test_signal_engine.py`.

## 2. Archivos nuevos

- `alpha_intraday/`
- `config_alpha_intraday.yaml`
- `requirements-alpha.txt`
- `.env.example`
- `.github/workflows/alpha-intraday.yml`
- `.github/workflows/alpha-intraday-monitor.yml`
- `.github/workflows/alpha-tests.yml`
- `supabase/alpha_intraday_schema.sql`
- `docs/alpha/`
- `tests/alpha_intraday/`
- Documentacion `ALPHA_INTRADIA_*.md`

## 3. Archivos modificados

- `README.md`
- `dashboard_utils.py`
- `docs/index.html`
- `docs/opportunities.html`

## 4. Funcionalidad completada

- Skeleton modular separado.
- Development mode por defecto.
- Schedule Alpha desactivado por defecto: los cron solo corren si `ALPHA_SCHEDULE_ENABLED=true`; `workflow_dispatch` sigue funcionando.
- Override operativo `ALPHA_DATA_PROVIDER=mock|alpaca`.
- LONG-only por enums y setups.
- Sin apalancamiento.
- Sin broker execution.
- Reloj NY con ventanas 09:25-10:20 y entrada 09:40-10:15 ET.
- Indicadores deterministas.
- Data-quality gate.
- Filtros duros de universo.
- Score 100 puntos por componentes.
- Risk sizing EUR/USD con acciones enteras.
- Setups condicionales.
- Telegram adapter con dedupe.
- Supabase schema con RLS.
- Dashboard Alpha en `docs/alpha/`.
- Replay con fixture.
- ProviderFactory `mock`/`alpaca`.
- ProductionReadinessReport granular.
- Alpaca bars oficial con retries, 403 entitlement, 429, timeouts, `sort=desc` y normalizacion cronologica ascendente del tramo mas reciente.
- Scanner sin datos sinteticos hardcodeados.
- Scanner sin targets calculados como `entry + risk * X`; entrada, stop y objetivos solo pasan si vienen como niveles tecnicos suministrados por proveedor/fixture.
- OR/VWAP regular excluyen premarket.
- Indicadores 5m sobre dataframe 5m resampleado y con warm-up historico real; si no hay suficientes barras, quedan como no disponibles.
- Quality 5m separa warm-up historico de disponibilidad de sesion actual: `indicator_history_5m_bars` y `current_session_5m_bars`.
- RSI de series cortas queda no disponible, no se fuerza a 100.
- `RSI5` significa RSI calculado sobre velas de 5 minutos; el periodo por defecto es configurable y queda en 14.
- MACD intradia usa parametros configurables `macd_fast`, `macd_slow` y `macd_signal`.
- 15m se mantiene conservador: antes de 09:45 ET la OR15 puede estar formando y no se inventa vela cerrada; si el quality gate exige una vela 15m cerrada, la ventana efectiva de senal definitiva empieza a las 09:45 ET aunque observacion/preseleccion empiece a las 09:40 ET.
- Fallos por simbolo en proveedores quedan en `BLOCKED` y no tumban la sesion completa.
- Production readiness bloquea si faltan latest trade, news/catalyst, index data verificado u otros proveedores requeridos.
- Session runner duradero 09:25-10:20 ET con clock/sleeper inyectable.
- Provider health real: `GREEN`, `DEGRADED`, `BLOCKED`, `NOT_CONFIGURED`, `FIXTURE`.

## 5. Tests ejecutados

```bash
.venv/bin/python tests/test_signal_engine.py
.venv/bin/python -m py_compile agent.py event_rumor_agent.py premium_agent_utils.py intraday_cashout_agent.py signal_engine.py signal_performance_agent.py alpha_intraday/*.py alpha_intraday/providers/*.py
.venv/bin/python -m alpha_intraday.cli validate-config
.venv/bin/python -m alpha_intraday.cli health
.venv/bin/python -m alpha_intraday.cli replay --fixture tests/alpha_intraday/fixtures/session_sample/
.venv/bin/python -m alpha_intraday.cli run-session --now 2026-07-08T09:25:00-04:00 --cadence-seconds 900 --max-iterations 3 --force
env -u ALPACA_API_KEY -u ALPACA_SECRET_KEY ALPHA_DATA_PROVIDER=alpaca .venv/bin/python -m alpha_intraday.cli --config config_alpha_intraday.yaml snapshot --now 2026-07-08T09:45:00-04:00
```

Ademas se ejecutaron 46 tests Alpha mediante runner local porque la venv no tenia `pytest` instalado.

## 6. Tests pasados/fallidos

- Pasados: legacy ligero, py_compile, config, replay, run-session fake, Alpaca sin credenciales como `NO OPERAR`, JSON, 46 tests Alpha.
- No ejecutado con pytest local: falta `pytest` en la venv local. El workflow `Alpha Intradia Tests` instala `requirements-alpha.txt`.
- CI GitHub Actions: validar `Alpha Intradia Tests` sobre el head final antes de marcar la PR como lista.

## 7. Servicios externos integrados

- Telegram reutiliza el adapter legacy.
- Alpaca tiene adapter inicial para latest quote y barras intradia con credenciales.
- Supabase tiene schema/RLS, adapter backend pendiente.

## 8. Servicios aun no configurados

- Alpaca latest trade separado pendiente.
- Finnhub/analyst provider real.
- News provider real.
- Macro/index providers reales.
- FX provider real.
- Supabase writes backend.

## 9. Secrets necesarios

```text
ALPACA_API_KEY
ALPACA_SECRET_KEY
FINNHUB_API_KEY
SUPABASE_SECRET_KEY
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
```

## 10. GitHub Variables necesarias

```text
ALPHA_MODE=development
ALPHA_LIVE_SIGNALS=false
ALPHA_TELEGRAM_ENABLED=false
ALPHA_SCHEDULE_ENABLED=false
ALPHA_DATA_PROVIDER=mock
ALPACA_DATA_FEED=iex
SUPABASE_URL=
TELEGRAM_CHAT_IDS=
```

## 11. Pasos manuales

1. Mergear la PR.
2. Ejecutar `Alpha Intradia V2` en Actions con `force=true` para poblar Pages.
3. Configurar secrets si quieres probar Alpaca/Telegram.
4. Ejecutar SQL de Supabase si quieres activar persistencia futura.
5. Revisar `https://diegosr-git.github.io/market-signal-agent/alpha/`.

## 12. Coste actual

0 EUR previsto usando GitHub, Pages, Telegram, Supabase Free y Alpaca Basic/IEX.

## 13. Que esta en development

- Datos fixture por defecto.
- Provider health marca fixtures como `FIXTURE`.
- `LIVE_SIGNAL_ALLOWED = FALSE`.
- Dashboard muestra banner de desarrollo.
- Telegram marca DEVELOPMENT.

## 14. Que impide production-ready

- Feed US completo no verificado.
- Latest trade/RVOL real no verificados.
- Market cap/analyst/news providers reales no configurados.
- VIX/US10Y/indices reales no configurados.
- EURUSD real no configurado.
- RLS Supabase no auditada en instancia real.
- Falta observacion paper durante semanas.

## 15. Proximo paso recomendado

Conectar Alpaca quotes/bars reales y un UniverseProvider fiable, manteniendo `ALPHA_MODE=development` hasta que los quality gates demuestren datos completos.

## 16. Ultimo hardening PR #16

- Rama: `codex/alpha-intradia-v2`.
- Commit hardening: `f585780`.
- Commit informe inicial: `b851b76`.
- Objetivo del commit: cerrar frescura/orden de barras Alpaca, warm-up real de indicadores, no fabricacion de niveles, provider health bloqueante, readiness de produccion estricta, schedule opt-in y override de proveedor.
- Estado funcional: base de desarrollo segura. No esta marcada como production-ready y no genera senales live.
