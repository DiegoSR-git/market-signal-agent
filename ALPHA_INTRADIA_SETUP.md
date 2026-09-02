# Alpha Intradia V2 - Setup

Esta guia es para poner Alpha en marcha sin tocar el sistema legacy.

## 1. Crear cuenta Alpaca

1. Entra en Alpaca.
2. Crea una cuenta de desarrollo/paper.
3. Copia `API Key` y `Secret Key`.
4. Usa `iex` como feed inicial gratuito/parcial.

## 2. Poner secrets en GitHub

Ve a:

```text
Repository > Settings > Secrets and variables > Actions > Secrets
```

Añade:

```text
ALPACA_API_KEY
ALPACA_SECRET_KEY
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
```

Opcionales:

```text
FINNHUB_API_KEY
SUPABASE_SECRET_KEY
```

## 3. Poner variables en GitHub

Ve a:

```text
Repository > Settings > Secrets and variables > Actions > Variables
```

Añade:

```text
ALPHA_MODE=development
ALPHA_LIVE_SIGNALS=false
ALPACA_DATA_FEED=iex
TELEGRAM_CHAT_IDS=123,456
SUPABASE_URL=
```

## 4. Configurar Supabase

1. Crea proyecto en Supabase Free.
2. Abre SQL Editor.
3. Ejecuta `supabase/alpha_intraday_schema.sql`.
4. Comprueba que RLS esta activo.
5. No copies `SUPABASE_SECRET_KEY` en ningun HTML o JS.

## 5. Configurar Pages

Tu repo ya publica `/docs`. Alpha aparece en:

```text
https://diegosr-git.github.io/market-signal-agent/alpha/
```

## 6. Ejecutar manualmente

En GitHub:

```text
Actions > Alpha Intradia V2 > Run workflow
```

Para probar fuera de ventana usa:

```text
force=true
telegram=false
```

## 7. Interpretar development mode

Si ves:

```text
MODO DESARROLLO
DATOS IEX / COBERTURA PARCIAL
NO UTILIZAR COMO SENAL REAL DE TRADING
```

es correcto. Alpha esta en modo seguro. No es una señal real.

## 8. Probar local

```bash
pip install -r requirements.txt -r requirements-alpha.txt
python -m alpha_intraday.cli validate-config
python -m alpha_intraday.cli health
python -m alpha_intraday.cli snapshot --dry-run
python -m alpha_intraday.cli replay --fixture tests/alpha_intraday/fixtures/session_sample/
```

## 9. Coste

Coste inicial: 0 EUR si usas GitHub Actions, Pages, Telegram, Supabase Free y Alpaca Basic/IEX.
