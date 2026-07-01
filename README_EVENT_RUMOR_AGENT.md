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
- Usa GDELT DOC API como fuente abierta.
- Usa Yahoo Finance para precio, RSI y momentum.
- Usa GitHub Models para convertir datos en resumen estructurado.
- Envía alertas por Telegram.
- Guarda snapshot, log y dashboard.

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

## Nota

Solo usa información pública. No usa información privilegiada ni ejecuta compras.
