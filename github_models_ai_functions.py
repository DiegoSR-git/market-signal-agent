
# =============================================================================
# GITHUB MODELS AI SUMMARY
# Add this block to agent.py before def main()
# =============================================================================

GITHUB_MODELS_TOKEN = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
GITHUB_MODELS_ENDPOINT = os.getenv("GITHUB_MODELS_ENDPOINT", "https://models.github.ai/inference/chat/completions")


def json_safe(obj):
    """
    Convierte objetos no serializables en JSON seguro para enviar a GitHub Models.
    Evita mandar DataFrames completos a la IA.
    """
    try:
        import pandas as _pd
        if isinstance(obj, _pd.DataFrame):
            return f"<dataframe rows={len(obj)} cols={list(obj.columns)}>"
        if isinstance(obj, _pd.Series):
            return obj.tail(10).tolist()
    except Exception:
        pass

    if isinstance(obj, dict):
        return {str(k): json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [json_safe(x) for x in obj[:20]]
    if isinstance(obj, tuple):
        return [json_safe(x) for x in obj[:20]]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj

    try:
        return float(obj)
    except Exception:
        return str(obj)


def build_ai_market_payload(metrics, scorepack, macro=None, stock_opportunities=None):
    etf = metrics.get("etf", {})
    fear = metrics.get("fear", {})
    funding = metrics.get("funding", {})
    oi_hist = metrics.get("oi_hist", {})
    oi_current = metrics.get("oi_current", {})
    mvrv = metrics.get("mvrv", {})

    payload = {
        "btc": {
            "price_eur": metrics.get("price"),
            "score": scorepack.get("score"),
            "status": scorepack.get("status"),
            "signal_types": scorepack.get("signal_types"),
            "market_regime": scorepack.get("market_regime"),
            "rsi_daily": metrics.get("rsi_daily"),
            "sma20": metrics.get("sma20"),
            "sma50": metrics.get("sma50"),
            "sma200": metrics.get("sma200"),
            "drawdown_30d_pct": metrics.get("dd30"),
            "drawdown_90d_pct": metrics.get("dd90"),
            "volatility_14d_pct": metrics.get("vol14"),
            "volatility_30d_pct": metrics.get("vol30"),
        },
        "etf_flows": {
            "date": etf.get("date"),
            "source": etf.get("source"),
            "total_musd": etf.get("total"),
            "ibit_musd": etf.get("ibit"),
            "stale_days": etf.get("stale_days"),
        },
        "sentiment_derivatives_onchain": {
            "fear_and_greed": fear.get("value"),
            "fear_classification": fear.get("classification"),
            "funding_latest": funding.get("latest"),
            "funding_avg_5": funding.get("avg_5"),
            "funding_negative_count_5": funding.get("negative_count_5"),
            "open_interest": oi_current.get("open_interest"),
            "open_interest_change_24h_pct": oi_hist.get("change_24h"),
            "open_interest_change_recent_pct": oi_hist.get("change_recent"),
            "mvrv_current": mvrv.get("value"),
            "mvrv_metric": mvrv.get("metric"),
        },
        "macro": macro or {},
        "stock_opportunities": stock_opportunities[:5] if stock_opportunities else [],
        "rules_output": {
            "reasons": scorepack.get("reasons", []),
            "blocks": scorepack.get("blocks", []),
            "actions": scorepack.get("actions", []),
        },
    }

    return json_safe(payload)


def fallback_rule_summary(metrics, scorepack):
    score = scorepack.get("score")
    status = scorepack.get("status")
    reasons = scorepack.get("reasons") or ["No hay señal relevante"]
    actions = scorepack.get("actions") or ["No comprar; seguir esperando"]
    blocks = scorepack.get("blocks") or ["Sin bloqueos críticos"]

    return (
        f"1) Diagnóstico: {status}, score {score}/100.\n"
        f"2) Lectura BTC: {reasons[0]}.\n"
        f"3) Lectura institucional/ETF: datos ETF no concluyentes o no actualizados.\n"
        f"4) Riesgo principal: {blocks[0]}.\n"
        f"5) Acción operativa: {actions[0]}.\n"
        f"6) Confianza: Media."
    )


def build_ai_prompt(payload):
    return (
        "Actúa como analista cuantitativo de mercado especializado en BTC, derivados, ETF flows y psicología de mercado.\n\n"
        "Recibirás un JSON con datos ya calculados por un motor cuantitativo. No inventes datos. "
        "No cambies precios. No recomiendes comprar si el motor de reglas no lo permite.\n\n"
        "Genera un resumen breve en español para Telegram.\n\n"
        "Formato obligatorio:\n"
        "1) Diagnóstico en una frase.\n"
        "2) Lectura BTC.\n"
        "3) Lectura institucional/ETF.\n"
        "4) Riesgo principal.\n"
        "5) Acción operativa.\n"
        "6) Nivel de confianza: Bajo / Medio / Alto.\n\n"
        "Reglas:\n"
        "- Máximo 180 palabras.\n"
        "- Tono directo y operativo.\n"
        "- Sin disclaimers genéricos.\n"
        "- Si no hay señal, dilo claramente.\n"
        "- Si ETF está N/A o stale, menciónalo como limitación.\n"
        "- La acción operativa debe respetar estrictamente rules_output.actions.\n"
        "- Los bloqueos deben respetar estrictamente rules_output.blocks.\n\n"
        "JSON:\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def call_github_models_summary(prompt, config):
    ai_cfg = config.get("ai_summary", {})
    model = ai_cfg.get("model", "openai/gpt-4.1-mini")
    max_tokens = int(ai_cfg.get("max_output_tokens", 450))
    temperature = float(ai_cfg.get("temperature", 0.2))

    if not GITHUB_MODELS_TOKEN:
        raise RuntimeError("Missing GITHUB_TOKEN/GH_TOKEN for GitHub Models")

    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {GITHUB_MODELS_TOKEN}",
        "X-GitHub-Api-Version": "2026-03-10",
        "Content-Type": "application/json",
    }

    body = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "Eres un analista cuantitativo. Debes resumir datos de mercado sin inventar información."
            },
            {
                "role": "user",
                "content": prompt
            },
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    r = requests.post(GITHUB_MODELS_ENDPOINT, headers=headers, json=body, timeout=45)
    r.raise_for_status()
    data = r.json()

    choices = data.get("choices", [])
    if not choices:
        raise RuntimeError(f"No GitHub Models choices: {data}")

    text = choices[0].get("message", {}).get("content", "").strip()
    if not text:
        raise RuntimeError(f"Empty GitHub Models response: {data}")

    return text


def generate_ai_summary(config, metrics, scorepack, macro=None, stock_opportunities=None):
    ai_cfg = config.get("ai_summary", {})

    if not ai_cfg.get("enabled", False):
        return fallback_rule_summary(metrics, scorepack)

    payload = build_ai_market_payload(metrics, scorepack, macro, stock_opportunities)
    prompt = build_ai_prompt(payload)

    try:
        return call_github_models_summary(prompt, config)
    except Exception as ex:
        print(f"GitHub Models AI summary error: {ex}")
        return fallback_rule_summary(metrics, scorepack)


# Wrap original btc_message to append AI summary in signal alerts.
_original_btc_message = btc_message

def btc_message(config, m, s, macro=None):
    msg = _original_btc_message(config, m, s, macro)

    if config.get("ai_summary", {}).get("send_in_signal_alerts", False):
        ai_text = generate_ai_summary(config, m, s, macro)
        msg += "\n\n<b>🧠 Resumen IA:</b>\n" + e(ai_text)

    return msg


# Override daily report runner to append AI summary.
_original_daily_report = daily_report

def run_daily_report(config, state, force=False):
    msg = _original_daily_report(config, state)

    if config.get("ai_summary", {}).get("send_in_daily_report", True):
        try:
            m = collect_btc_metrics(config)
            macro = macro_snapshot(config)
            s = score_btc(config, state, m, macro)
            ops = scan_stocks(config) if config.get("stocks", {}).get("enabled", False) else []
            ai_text = generate_ai_summary(config, m, s, macro, ops)
            msg += "\n\n<b>🧠 Resumen IA:</b>\n" + e(ai_text)
        except Exception as ex:
            msg += "\n\n<b>🧠 Resumen IA:</b>\n" + e(f"No disponible: {ex}")

    print(msg)
    if force or config.get("reports", {}).get("send_daily", True):
        send_telegram(msg, buttons=default_buttons())


# Override weekly report runner to append AI summary.
_original_weekly_report = weekly_report

def run_weekly_report(config, state, force=False):
    msg = _original_weekly_report(config, state)

    if config.get("ai_summary", {}).get("send_in_weekly_report", True):
        try:
            m = collect_btc_metrics(config)
            macro = macro_snapshot(config)
            s = score_btc(config, state, m, macro)
            ai_text = generate_ai_summary(config, m, s, macro)
            msg += "\n\n<b>🧠 Resumen IA:</b>\n" + e(ai_text)
        except Exception as ex:
            msg += "\n\n<b>🧠 Resumen IA:</b>\n" + e(f"No disponible: {ex}")

    print(msg)
    if force or config.get("reports", {}).get("send_weekly", True):
        send_telegram(msg, buttons=default_buttons())
