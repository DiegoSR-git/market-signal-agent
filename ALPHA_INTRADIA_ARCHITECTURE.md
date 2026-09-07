# Alpha Intradia V2 - Arquitectura

Alpha Intradia entra como modulo separado en `alpha_intraday/`. El sistema legacy sigue funcionando y no se reemplaza.

Flujo objetivo:

```text
Providers externos
GitHub Actions
alpha_intraday/
data-quality + indicadores + scanner + scoring + risk
Telegram + Supabase
GitHub Pages docs/alpha/
futura API para GPT
```

Principios:

- LONG-only sobre acciones ordinarias USA large cap.
- Sin apalancamiento.
- Sin broker execution.
- Modo `development` por defecto.
- No inventar precios, quotes, velas, analistas, market cap ni noticias.
- Ante duda: `NO OPERAR`.

Modulos:

- `models.py`: dataclasses y enums del dominio.
- `config.py`: YAML/env y validacion.
- `market_clock.py`: horario NY con `ZoneInfo("America/New_York")`.
- `indicators.py`: SMA, EMA, RSI, MACD, ATR, VWAP, OR, RVOL.
- `data_quality.py`: freshness, spread y hard gates.
- `providers/`: interfaces, fixtures y adapter Alpaca inicial.
- `provider_factory.py`: selecciona mock/alpaca segun config sin sustitucion silenciosa en production.
- `readiness.py`: readiness granular `PASS/FAIL/NOT_CONFIGURED`.
- `market_calendar.py`: abstraccion de calendario con fallback estatico de desarrollo.
- `session.py`: sesion duradera 09:25-10:20 ET con clock/sleeper inyectable.
- `universe.py`: filtros duros de universo.
- `scoring.py`: score determinista 100 puntos.
- `setups.py`: BREAKOUT, VWAP_RECLAIM, CONTROLLED_PULLBACK.
- `risk.py`: sizing EUR/USD sin apalancamiento.
- `scanner.py`: ensamblado de snapshot.
- `signal_engine.py`: salida JSON/HTML/texto.
- `telegram.py`: adapter con dedupe por transicion.
- `storage.py` y `journal.py`: persistencia local y base Supabase futura.

Production-ready no significa "tests pasan". Requiere proveedores reales, feed completo, RLS auditada y semanas de observacion paper. El scanner general no contiene datos de mercado sinteticos: si se usan fixtures, estos entran desde providers fixture/replay y aparecen como `FIXTURE` en provider health.
