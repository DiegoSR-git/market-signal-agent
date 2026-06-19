#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Aplica integración de GitHub Models al Market Signal Agent.

Uso:
  python apply_github_models_patch.py

Hace:
- Inserta funciones de resumen IA en agent.py antes de def main()
- Añade bloque ai_summary a config.yaml
- Añade permissions: models: read a workflows
- Añade GITHUB_TOKEN al env de workflows
"""

from pathlib import Path
import re

ROOT = Path(".")
AGENT = ROOT / "agent.py"
CONFIG = ROOT / "config.yaml"
WORKFLOWS = ROOT / ".github" / "workflows"

AI_BLOCK = '\n# =============================================================================\n# GITHUB MODELS AI SUMMARY\n# Add this block to agent.py before def main()\n# =============================================================================\n\nGITHUB_MODELS_TOKEN = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")\nGITHUB_MODELS_ENDPOINT = os.getenv("GITHUB_MODELS_ENDPOINT", "https://models.github.ai/inference/chat/completions")\n\n\ndef json_safe(obj):\n    """\n    Convierte objetos no serializables en JSON seguro para enviar a GitHub Models.\n    Evita mandar DataFrames completos a la IA.\n    """\n    try:\n        import pandas as _pd\n        if isinstance(obj, _pd.DataFrame):\n            return f"<dataframe rows={len(obj)} cols={list(obj.columns)}>"\n        if isinstance(obj, _pd.Series):\n            return obj.tail(10).tolist()\n    except Exception:\n        pass\n\n    if isinstance(obj, dict):\n        return {str(k): json_safe(v) for k, v in obj.items()}\n    if isinstance(obj, list):\n        return [json_safe(x) for x in obj[:20]]\n    if isinstance(obj, tuple):\n        return [json_safe(x) for x in obj[:20]]\n    if isinstance(obj, (str, int, float, bool)) or obj is None:\n        return obj\n\n    try:\n        return float(obj)\n    except Exception:\n        return str(obj)\n\n\ndef build_ai_market_payload(metrics, scorepack, macro=None, stock_opportunities=None):\n    etf = metrics.get("etf", {})\n    fear = metrics.get("fear", {})\n    funding = metrics.get("funding", {})\n    oi_hist = metrics.get("oi_hist", {})\n    oi_current = metrics.get("oi_current", {})\n    mvrv = metrics.get("mvrv", {})\n\n    payload = {\n        "btc": {\n            "price_eur": metrics.get("price"),\n            "score": scorepack.get("score"),\n            "status": scorepack.get("status"),\n            "signal_types": scorepack.get("signal_types"),\n            "market_regime": scorepack.get("market_regime"),\n            "rsi_daily": metrics.get("rsi_daily"),\n            "sma20": metrics.get("sma20"),\n            "sma50": metrics.get("sma50"),\n            "sma200": metrics.get("sma200"),\n            "drawdown_30d_pct": metrics.get("dd30"),\n            "drawdown_90d_pct": metrics.get("dd90"),\n            "volatility_14d_pct": metrics.get("vol14"),\n            "volatility_30d_pct": metrics.get("vol30"),\n        },\n        "etf_flows": {\n            "date": etf.get("date"),\n            "source": etf.get("source"),\n            "total_musd": etf.get("total"),\n            "ibit_musd": etf.get("ibit"),\n            "stale_days": etf.get("stale_days"),\n        },\n        "sentiment_derivatives_onchain": {\n            "fear_and_greed": fear.get("value"),\n            "fear_classification": fear.get("classification"),\n            "funding_latest": funding.get("latest"),\n            "funding_avg_5": funding.get("avg_5"),\n            "funding_negative_count_5": funding.get("negative_count_5"),\n            "open_interest": oi_current.get("open_interest"),\n            "open_interest_change_24h_pct": oi_hist.get("change_24h"),\n            "open_interest_change_recent_pct": oi_hist.get("change_recent"),\n            "mvrv_current": mvrv.get("value"),\n            "mvrv_metric": mvrv.get("metric"),\n        },\n        "macro": macro or {},\n        "stock_opportunities": stock_opportunities[:5] if stock_opportunities else [],\n        "rules_output": {\n            "reasons": scorepack.get("reasons", []),\n            "blocks": scorepack.get("blocks", []),\n            "actions": scorepack.get("actions", []),\n        },\n    }\n\n    return json_safe(payload)\n\n\ndef fallback_rule_summary(metrics, scorepack):\n    score = scorepack.get("score")\n    status = scorepack.get("status")\n    reasons = scorepack.get("reasons") or ["No hay señal relevante"]\n    actions = scorepack.get("actions") or ["No comprar; seguir esperando"]\n    blocks = scorepack.get("blocks") or ["Sin bloqueos críticos"]\n\n    return (\n        f"1) Diagnóstico: {status}, score {score}/100.\\n"\n        f"2) Lectura BTC: {reasons[0]}.\\n"\n        f"3) Lectura institucional/ETF: datos ETF no concluyentes o no actualizados.\\n"\n        f"4) Riesgo principal: {blocks[0]}.\\n"\n        f"5) Acción operativa: {actions[0]}.\\n"\n        f"6) Confianza: Media."\n    )\n\n\ndef build_ai_prompt(payload):\n    return (\n        "Actúa como analista cuantitativo de mercado especializado en BTC, derivados, ETF flows y psicología de mercado.\\n\\n"\n        "Recibirás un JSON con datos ya calculados por un motor cuantitativo. No inventes datos. "\n        "No cambies precios. No recomiendes comprar si el motor de reglas no lo permite.\\n\\n"\n        "Genera un resumen breve en español para Telegram.\\n\\n"\n        "Formato obligatorio:\\n"\n        "1) Diagnóstico en una frase.\\n"\n        "2) Lectura BTC.\\n"\n        "3) Lectura institucional/ETF.\\n"\n        "4) Riesgo principal.\\n"\n        "5) Acción operativa.\\n"\n        "6) Nivel de confianza: Bajo / Medio / Alto.\\n\\n"\n        "Reglas:\\n"\n        "- Máximo 180 palabras.\\n"\n        "- Tono directo y operativo.\\n"\n        "- Sin disclaimers genéricos.\\n"\n        "- Si no hay señal, dilo claramente.\\n"\n        "- Si ETF está N/A o stale, menciónalo como limitación.\\n"\n        "- La acción operativa debe respetar estrictamente rules_output.actions.\\n"\n        "- Los bloqueos deben respetar estrictamente rules_output.blocks.\\n\\n"\n        "JSON:\\n"\n        f"{json.dumps(payload, ensure_ascii=False, indent=2)}"\n    )\n\n\ndef call_github_models_summary(prompt, config):\n    ai_cfg = config.get("ai_summary", {})\n    model = ai_cfg.get("model", "openai/gpt-4.1-mini")\n    max_tokens = int(ai_cfg.get("max_output_tokens", 450))\n    temperature = float(ai_cfg.get("temperature", 0.2))\n\n    if not GITHUB_MODELS_TOKEN:\n        raise RuntimeError("Missing GITHUB_TOKEN/GH_TOKEN for GitHub Models")\n\n    headers = {\n        "Accept": "application/vnd.github+json",\n        "Authorization": f"Bearer {GITHUB_MODELS_TOKEN}",\n        "X-GitHub-Api-Version": "2026-03-10",\n        "Content-Type": "application/json",\n    }\n\n    body = {\n        "model": model,\n        "messages": [\n            {\n                "role": "system",\n                "content": "Eres un analista cuantitativo. Debes resumir datos de mercado sin inventar información."\n            },\n            {\n                "role": "user",\n                "content": prompt\n            },\n        ],\n        "temperature": temperature,\n        "max_tokens": max_tokens,\n    }\n\n    r = requests.post(GITHUB_MODELS_ENDPOINT, headers=headers, json=body, timeout=45)\n    r.raise_for_status()\n    data = r.json()\n\n    choices = data.get("choices", [])\n    if not choices:\n        raise RuntimeError(f"No GitHub Models choices: {data}")\n\n    text = choices[0].get("message", {}).get("content", "").strip()\n    if not text:\n        raise RuntimeError(f"Empty GitHub Models response: {data}")\n\n    return text\n\n\ndef generate_ai_summary(config, metrics, scorepack, macro=None, stock_opportunities=None):\n    ai_cfg = config.get("ai_summary", {})\n\n    if not ai_cfg.get("enabled", False):\n        return fallback_rule_summary(metrics, scorepack)\n\n    payload = build_ai_market_payload(metrics, scorepack, macro, stock_opportunities)\n    prompt = build_ai_prompt(payload)\n\n    try:\n        return call_github_models_summary(prompt, config)\n    except Exception as ex:\n        print(f"GitHub Models AI summary error: {ex}")\n        return fallback_rule_summary(metrics, scorepack)\n\n\n# Wrap original btc_message to append AI summary in signal alerts.\n_original_btc_message = btc_message\n\ndef btc_message(config, m, s, macro=None):\n    msg = _original_btc_message(config, m, s, macro)\n\n    if config.get("ai_summary", {}).get("send_in_signal_alerts", False):\n        ai_text = generate_ai_summary(config, m, s, macro)\n        msg += "\\n\\n<b>🧠 Resumen IA:</b>\\n" + e(ai_text)\n\n    return msg\n\n\n# Override daily report runner to append AI summary.\n_original_daily_report = daily_report\n\ndef run_daily_report(config, state, force=False):\n    msg = _original_daily_report(config, state)\n\n    if config.get("ai_summary", {}).get("send_in_daily_report", True):\n        try:\n            m = collect_btc_metrics(config)\n            macro = macro_snapshot(config)\n            s = score_btc(config, state, m, macro)\n            ops = scan_stocks(config) if config.get("stocks", {}).get("enabled", False) else []\n            ai_text = generate_ai_summary(config, m, s, macro, ops)\n            msg += "\\n\\n<b>🧠 Resumen IA:</b>\\n" + e(ai_text)\n        except Exception as ex:\n            msg += "\\n\\n<b>🧠 Resumen IA:</b>\\n" + e(f"No disponible: {ex}")\n\n    print(msg)\n    if force or config.get("reports", {}).get("send_daily", True):\n        send_telegram(msg, buttons=default_buttons())\n\n\n# Override weekly report runner to append AI summary.\n_original_weekly_report = weekly_report\n\ndef run_weekly_report(config, state, force=False):\n    msg = _original_weekly_report(config, state)\n\n    if config.get("ai_summary", {}).get("send_in_weekly_report", True):\n        try:\n            m = collect_btc_metrics(config)\n            macro = macro_snapshot(config)\n            s = score_btc(config, state, m, macro)\n            ai_text = generate_ai_summary(config, m, s, macro)\n            msg += "\\n\\n<b>🧠 Resumen IA:</b>\\n" + e(ai_text)\n        except Exception as ex:\n            msg += "\\n\\n<b>🧠 Resumen IA:</b>\\n" + e(f"No disponible: {ex}")\n\n    print(msg)\n    if force or config.get("reports", {}).get("send_weekly", True):\n        send_telegram(msg, buttons=default_buttons())\n'

CONFIG_BLOCK = '\nai_summary:\n  enabled: true\n  provider: github_models\n  model: openai/gpt-4.1-mini\n  max_output_tokens: 450\n  temperature: 0.2\n\n  # Recomendación para seguir gratis: IA solo en daily/weekly.\n  send_in_signal_alerts: false\n  send_in_daily_report: true\n  send_in_weekly_report: true\n'

def patch_agent():
    text = AGENT.read_text(encoding="utf-8")

    if "def call_github_models_summary" in text:
        print("agent.py ya tiene GitHub Models integrado.")
        return

    marker = "\ndef main():"
    if marker not in text:
        raise RuntimeError("No encuentro 'def main()' en agent.py")

    text = text.replace(marker, "\n" + AI_BLOCK + "\n" + marker, 1)
    AGENT.write_text(text, encoding="utf-8")
    print("agent.py parcheado.")

def patch_config():
    text = CONFIG.read_text(encoding="utf-8")

    if "ai_summary:" in text:
        print("config.yaml ya tiene ai_summary.")
        return

    text = text.rstrip() + "\n\n" + CONFIG_BLOCK.lstrip()
    CONFIG.write_text(text, encoding="utf-8")
    print("config.yaml parcheado.")

def ensure_models_permission(text):
    if "models: read" in text:
        return text

    if re.search(r"(?m)^permissions:\s*$", text):
        return re.sub(r"(?m)^permissions:\s*$", "permissions:\n  contents: write\n  models: read", text, count=1)

    if "\njobs:" in text:
        return text.replace("\njobs:", "\npermissions:\n  contents: write\n  models: read\n\njobs:", 1)

    return text

def ensure_github_token_env(text):
    if "GITHUB_TOKEN:" in text:
        return text

    if "TELEGRAM_CHAT_ID:" in text:
        return text.replace(
            "TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}",
            "TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}\n          GITHUB_TOKEN: ${{ github.token }}",
        )

    return text

def patch_workflows():
    if not WORKFLOWS.exists():
        print("No existe .github/workflows; salto workflows.")
        return

    for wf in WORKFLOWS.glob("*.yml"):
        text = wf.read_text(encoding="utf-8")
        new = ensure_models_permission(text)
        new = ensure_github_token_env(new)

        if new != text:
            wf.write_text(new, encoding="utf-8")
            print(f"{wf} parcheado.")
        else:
            print(f"{wf} sin cambios.")

def main():
    patch_agent()
    patch_config()
    patch_workflows()
    print("\nListo. Haz commit y prueba Daily Market Brief.")

if __name__ == "__main__":
    main()
