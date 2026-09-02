# Alpha Intradia V2 - Data Sources

| Campo | Proveedor inicial | Frecuencia | Freshness requerida | Critico | Fallback | Production-ready |
| --- | --- | --- | --- | --- | --- | --- |
| Price | Alpaca latest trade futuro / fixture dev | live | <= 5 min hard gate | si | no | no |
| Bid/Ask | Alpaca latest quote | live | segundos configurables | si | no | parcial IEX |
| Bars 1m/5m/15m | Alpaca bars futuro / fixture dev | intradia | <= 120s | si | no | no |
| Market cap | UniverseProvider no configurado | diario | cache con expiry | si | fixture dev | no |
| Analysts | AnalystProvider/Finnhub futuro | diario | cache con expiry | si | no | no |
| News | NewsProvider futuro | 24h | cache con expiry | no, pero suma score | no | no |
| VIX | MacroProvider futuro | intradia | configurable | si para production | no | no |
| US10Y | MacroProvider futuro | intradia | configurable | si para production | no | no |
| S&P500 index | IndexDataProvider futuro | intradia | configurable | no si se marca unavailable | SPY proxy declarado | no |
| Nasdaq100 index | IndexDataProvider futuro | intradia | configurable | no si se marca unavailable | QQQ proxy declarado | no |
| EURUSD | FXProvider futuro / fixture dev | intradia | configurable | si para sizing | no | no |

Notas:

- SPY no se etiqueta como S&P500 real. Es proxy.
- QQQ no se etiqueta como Nasdaq100 real. Es proxy.
- IEX implica cobertura parcial. En development se muestra de forma visible.
- Si SIP devuelve 403/entitlement, Alpha debe bloquear produccion y no hacer fallback silencioso.

Fuente Alpaca verificada para quote:

- `GET https://data.alpaca.markets/v2/stocks/{symbol}/quotes/latest`
- Campos usados: `quote.t`, `quote.bp`, `quote.ap`, `quote.bs`, `quote.as`.
