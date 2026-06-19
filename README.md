# Market Signal Agent Pro Free

Agente gratuito de vigilancia de BTC, bolsa/ETFs y macro con alertas Telegram.

## Qué incluye

- BTC/EUR con fallback CoinGecko → Coinbase → Kraken.
- RSI, SMA20/SMA50/SMA200, drawdowns, volatilidad realizada.
- Niveles de órdenes BTC con estado persistente.
- Funding BTCUSDT y Open Interest desde Binance Futures.
- Fear & Greed Index.
- MVRV current ratio desde CoinMetrics Community API, si está disponible.
- ETF flows con doble modo:
  - Farside si corre local/self-hosted.
  - Variables manuales GitHub si Farside devuelve 403.
- Macro: SPY, QQQ, VIX, DXY, 10Y vía Yahoo Finance.
- Watchlist acciones/ETFs con Yahoo Finance y fallback Stooq.
- Alertas por Telegram con botones.
- Anti-spam mediante state.json.
- Reporte diario, reporte semanal, healthcheck y backtest básico.
- Dashboard HTML en docs/dashboard.html.

## Secrets obligatorios

GitHub → Settings → Secrets and variables → Actions → Secrets:

```text
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
```

## Variables opcionales para ETF flows

GitHub → Settings → Secrets and variables → Actions → Variables:

```text
ETF_DATE
ETF_TOTAL_MUSD
ETF_IBIT_MUSD
```

Ejemplo:

```text
ETF_DATE = 2026-06-18
ETF_TOTAL_MUSD = -96.7
ETF_IBIT_MUSD = 0.0
```

## Probar manualmente

```text
Actions → Market Signal Agent → Run workflow → force=true
```

## Ejecutar local

```bash
pip install -r requirements.txt
python agent.py --mode signal --force
python agent.py --mode daily --force
python agent.py --mode weekly --force
python agent.py --mode health --force
python agent.py --mode backtest --force
```

## Modos

```text
signal    BTC + stocks, con umbrales/cooldown
btc       solo BTC
stocks    solo watchlist acciones/ETFs
daily     daily market brief
weekly    weekly regime report
health    healthcheck de fuentes
dashboard regenera docs/dashboard.html
backtest  backtest básico RSI BTC
all       señal BTC + stocks
```

## GitHub Pages opcional

Para ver el dashboard:

```text
Settings → Pages → Deploy from branch → main → /docs
```

## Nota sobre Farside

Farside puede devolver 403 desde GitHub-hosted runners. Por eso el agente soporta variables manuales de ETF flows. Si quieres scraping automático de Farside, usa self-hosted runner desde tu ordenador.


## GitHub Models / Resumen IA

Esta versión incluye resumen en lenguaje natural usando GitHub Models directamente desde GitHub Actions.

No necesitas una API key externa. El workflow usa:

```yaml
GITHUB_TOKEN: ${{ github.token }}
```

y permisos:

```yaml
permissions:
  contents: write
  models: read
```

Configuración por defecto en `config.yaml`:

```yaml
ai_summary:
  enabled: true
  provider: github_models
  model: openai/gpt-4.1-mini
  send_in_signal_alerts: false
  send_in_daily_report: true
  send_in_weekly_report: true
```

Recomendación: deja `send_in_signal_alerts: false` para no gastar cuota gratuita cada 30 minutos. La IA se usará en el reporte diario y semanal.

Para probar:

```text
Actions → Daily Market Brief → Run workflow
```

El mensaje de Telegram incluirá un bloque:

```text
🧠 Resumen IA:
1) Diagnóstico...
2) Lectura BTC...
3) Lectura institucional/ETF...
4) Riesgo principal...
5) Acción operativa...
6) Confianza...
```
