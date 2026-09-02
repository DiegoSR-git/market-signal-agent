# Alpha Intradia V2 - Seguridad

Reglas duras:

- No commitear claves reales.
- No imprimir secrets en logs.
- GitHub Pages no puede contener `SUPABASE_SECRET_KEY`.
- GitHub Pages solo puede leer datos publicos mediante clave publishable/anon y RLS.
- Backend en GitHub Actions escribe con credencial secreta.
- No hay `submit_order`, ordenes market ni ejecucion automatica.

Secrets GitHub:

```text
ALPACA_API_KEY
ALPACA_SECRET_KEY
FINNHUB_API_KEY
SUPABASE_SECRET_KEY
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
```

Variables GitHub:

```text
ALPHA_MODE=development
ALPHA_LIVE_SIGNALS=false
ALPACA_DATA_FEED=iex
SUPABASE_URL=
TELEGRAM_CHAT_IDS=
```

Supabase:

- Ejecutar `supabase/alpha_intraday_schema.sql`.
- Revisar que RLS esta habilitado.
- Mantener SELECT anon solo para datos no sensibles.
- No crear politicas anon para INSERT/UPDATE/DELETE.

Checklist production-ready:

- [ ] full US market feed
- [ ] live quote verified
- [ ] bid/ask verified
- [ ] complete intraday bars
- [ ] reliable RVOL history
- [ ] market cap provider
- [ ] >=8 analysts verified
- [ ] analyst median target verified
- [ ] news/catalyst source
- [ ] VIX source
- [ ] US10Y source
- [ ] S&P500 index source
- [ ] Nasdaq100 index source
- [ ] EURUSD source
- [ ] Supabase RLS audited
- [ ] Telegram tested
- [ ] replay tests passed
- [ ] several weeks paper observation

Mientras falte un componente critico: `PRODUCTION_READY = FALSE`.
