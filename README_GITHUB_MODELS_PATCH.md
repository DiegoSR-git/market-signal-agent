# Patch GitHub Models AI Summary

Este paquete añade resumen en lenguaje natural usando GitHub Models, sin Gemini ni API externa.

## Requisitos

GitHub Models usa el `GITHUB_TOKEN` dentro de GitHub Actions si el workflow tiene:

```yaml
permissions:
  models: read
```

En workflows que también hacen commit de `state.json`/dashboard, deja:

```yaml
permissions:
  contents: write
  models: read
```

## Instalar

Copia `apply_github_models_patch.py` a la raíz de tu repo y ejecuta:

```bash
python apply_github_models_patch.py
git add .
git commit -m "Add GitHub Models AI summaries"
git push
```

## Probar

Ejecuta:

```text
Actions → Daily Market Brief → Run workflow
```

El daily report debe incluir:

```text
🧠 Resumen IA:
1) Diagnóstico...
```

## Configuración añadida

```yaml
ai_summary:
  enabled: true
  provider: github_models
  model: openai/gpt-4.1-mini
  max_output_tokens: 450
  temperature: 0.2
  send_in_signal_alerts: false
  send_in_daily_report: true
  send_in_weekly_report: true
```

## Importante

Para mantenerlo gratis, deja `send_in_signal_alerts: false`.
Así la IA solo se usa en reportes diarios/semanales, no cada 30 minutos.
