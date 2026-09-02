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

## 5. Tests ejecutados

```bash
.venv/bin/python tests/test_signal_engine.py
.venv/bin/python -m py_compile agent.py event_rumor_agent.py premium_agent_utils.py intraday_cashout_agent.py signal_engine.py signal_performance_agent.py alpha_intraday/*.py alpha_intraday/providers/*.py
.venv/bin/python -m alpha_intraday.cli validate-config
.venv/bin/python -m alpha_intraday.cli health
.venv/bin/python -m alpha_intraday.cli replay --fixture tests/alpha_intraday/fixtures/session_sample/
```

Ademas se ejecutaron 17 tests Alpha mediante runner local porque la venv no tenia `pytest` instalado.

## 6. Tests pasados/fallidos

- Pasados: legacy ligero, py_compile, config, health, replay, JSON, 17 tests Alpha.
- No ejecutado con pytest local: falta `pytest` en la venv local. El workflow `Alpha Intradia Tests` instala `requirements-alpha.txt`.

## 7. Servicios externos integrados

- Telegram reutiliza el adapter legacy.
- Alpaca tiene adapter inicial para latest quote con credenciales.
- Supabase tiene schema/RLS, adapter backend pendiente.

## 8. Servicios aun no configurados

- Alpaca bars/trades completos.
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
- `LIVE_SIGNAL_ALLOWED = FALSE`.
- Dashboard muestra banner de desarrollo.
- Telegram marca DEVELOPMENT.

## 14. Que impide production-ready

- Feed US completo no verificado.
- Intraday bars/RVOL real no verificados.
- Market cap/analyst/news providers reales no configurados.
- VIX/US10Y/indices reales no configurados.
- EURUSD real no configurado.
- RLS Supabase no auditada en instancia real.
- Falta observacion paper durante semanas.

## 15. Proximo paso recomendado

Conectar Alpaca quotes/bars reales y un UniverseProvider fiable, manteniendo `ALPHA_MODE=development` hasta que los quality gates demuestren datos completos.
