# Event Rumor Agent

Agente gratuito para vigilar eventos corporativos tecnológicos, rumores públicos y posibles ventanas "buy the rumor".

## Archivos

```text
event_rumor_agent.py
config_events.yaml
.github/workflows/event-rumor-agent.yml
docs/event_rumor_dashboard.html
README_EVENT_RUMOR_AGENT.md
```

## Qué hace

- Busca noticias recientes sobre eventos corporativos y filtraciones públicas.
- Usa Google News RSS como fuente oportunista.
- Puede usar GDELT DOC API como fuente abierta, con backoff para evitar 429.
- Usa Yahoo Finance para precio, RSI y momentum.
- Usa GitHub Models para convertir datos en resumen estructurado.
- Envía alertas por Telegram.
- Guarda snapshot, log y dashboard.
- Puntúa oportunidades públicas por catalizadores, rumores, momentum y ventana temporal.

## Requisitos

Ya tienes estos secrets:

```text
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
```

Opcional para varios chats:

```text
TELEGRAM_CHAT_IDS
```

GitHub Models funciona con:

```yaml
permissions:
  models: read
```

y:

```yaml
GITHUB_TOKEN: ${{ github.token }}
```

## Prueba manual

```text
Actions → Event Rumor Agent → Run workflow → force=true
```

## Producción

Corre tres veces al día en días laborables:

```yaml
cron: "20 7,13,20 * * 1-5"
```

## Configuración

Edita `config_events.yaml` para cambiar empresas, eventos y palabras clave.

Parámetros recomendados:

```yaml
news:
  use_google_news_rss: true
  use_gdelt: false
  max_companies_per_run: 12
  max_queries_per_company: 6
  max_articles_per_company: 24
  max_articles_per_query: 3
```

`use_gdelt` queda desactivado por defecto porque GDELT suele responder con `429 Too Many Requests` o timeouts cuando se amplía el universo de empresas. Si quieres un barrido más profundo, actívalo puntualmente y el agente aplicará timeout, backoff y límite de errores por ejecución.

Para probar sin enviar Telegram:

```bash
python event_rumor_agent.py --dry-run --force --max-companies 3
```

Para ampliar el universo, añade bloques en `companies`. El agente ya incluye una lista más amplia de mega-cap tech, semiconductores, software enterprise y nombres de crecimiento, pero solo procesa `max_companies_per_run` en cada ejecución para mantener controladas las peticiones.

## Nota

Solo usa información pública. No usa información privilegiada ni ejecuta compras.
