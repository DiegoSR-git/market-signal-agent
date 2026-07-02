#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import csv
import html
import json
import os
import re
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import quote_plus

import pandas as pd
import requests
import yaml

from dashboard_utils import render_page, render_home_dashboard


GITHUB_MODELS_ENDPOINT = os.getenv(
    "GITHUB_MODELS_ENDPOINT",
    "https://models.github.ai/inference/chat/completions",
)
GITHUB_MODELS_TOKEN = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
TELEGRAM_CHAT_IDS = os.getenv("TELEGRAM_CHAT_IDS")
TELEGRAM_MAX_MESSAGE_CHARS = 3900
SESSION = requests.Session()


def log(message):
    print(message, flush=True)


def utc_now():
    return datetime.now(timezone.utc)


def iso_now():
    return utc_now().isoformat()


def esc(value):
    return html.escape("" if value is None else str(value))


def safe_float(value, default=None):
    try:
        if value in [None, "", "N/A"]:
            return default
        return float(value)
    except Exception:
        return default


def clamp(value, lo=0, hi=100):
    return max(lo, min(hi, value))


def pct_change(current, previous):
    if current is None or previous in [None, 0]:
        return None
    return (current / previous - 1) * 100


def score_level(score):
    score = safe_float(score, 0)
    if score >= 80:
        return "alto"
    if score >= 65:
        return "medio"
    return "vigilancia"


def fmt_float(value, decimals=2):
    value = safe_float(value)
    return "N/A" if value is None else f"{value:.{decimals}f}"


def fmt_pct(value, decimals=1):
    value = safe_float(value)
    return "N/A" if value is None else f"{value:+.{decimals}f}%"


def load_yaml(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def read_json(path, default):
    p = Path(path)
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as ex:
        log(f"JSON read error {path}: {ex}")
        return default


def write_json(path, data):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def load_state(path):
    state = read_json(path, {"last_alerts": {}, "last_run_utc": None})
    state.setdefault("last_alerts", {})
    return state


def save_state(path, state):
    state["last_run_utc"] = iso_now()
    write_json(path, state)


def append_csv(path, fieldnames, row):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    exists = p.exists()
    with p.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not exists:
            writer.writeheader()
        writer.writerow({k: row.get(k, "") for k in fieldnames})


def http_timeout(config=None, read=None):
    http = (config or {}).get("http", {})
    connect = float(http.get("connect_timeout", 6))
    read_timeout = float(read or http.get("read_timeout", 14))
    return (connect, read_timeout)


def request_json(url, config=None, params=None, headers=None, retries=None, read_timeout=None):
    http = (config or {}).get("http", {})
    attempts = int(retries if retries is not None else http.get("retries", 1)) + 1
    delay = float(http.get("retry_delay_seconds", 1.0))
    default_headers = {"User-Agent": http.get("user_agent", "market-signal-agent/1.0")}
    if headers:
        default_headers.update(headers)
    last_error = None
    for attempt in range(attempts):
        try:
            r = SESSION.get(
                url,
                params=params,
                headers=default_headers,
                timeout=http_timeout(config, read=read_timeout),
            )
            log(f"HTTP {r.status_code} {r.url[:180]}")
            if r.status_code in [429, 500, 502, 503, 504] and attempt < attempts - 1:
                time.sleep(delay * (attempt + 1))
                continue
            r.raise_for_status()
            return r.json()
        except Exception as ex:
            last_error = ex
            if attempt < attempts - 1:
                time.sleep(delay * (attempt + 1))
    raise last_error


def request_text(url, config=None, params=None, headers=None, retries=None, read_timeout=None):
    http = (config or {}).get("http", {})
    attempts = int(retries if retries is not None else http.get("retries", 1)) + 1
    delay = float(http.get("retry_delay_seconds", 1.0))
    default_headers = {"User-Agent": http.get("user_agent", "market-signal-agent/1.0")}
    if headers:
        default_headers.update(headers)
    last_error = None
    for attempt in range(attempts):
        try:
            r = SESSION.get(
                url,
                params=params,
                headers=default_headers,
                timeout=http_timeout(config, read=read_timeout),
            )
            log(f"HTTP {r.status_code} {r.url[:180]}")
            if r.status_code in [429, 500, 502, 503, 504] and attempt < attempts - 1:
                time.sleep(delay * (attempt + 1))
                continue
            r.raise_for_status()
            return r.text
        except Exception as ex:
            last_error = ex
            if attempt < attempts - 1:
                time.sleep(delay * (attempt + 1))
    raise last_error


def get_telegram_chat_ids():
    ids = []
    if TELEGRAM_CHAT_IDS:
        ids.extend(x.strip() for x in TELEGRAM_CHAT_IDS.split(",") if x.strip())
    if TELEGRAM_CHAT_ID:
        ids.append(TELEGRAM_CHAT_ID.strip())
    out = []
    for item in ids:
        if item not in out:
            out.append(item)
    return out


def split_telegram_message(message, max_chars=TELEGRAM_MAX_MESSAGE_CHARS):
    if len(message) <= max_chars:
        return [message]
    chunks, current = [], []
    current_len = 0
    for block in message.split("\n\n"):
        extra = len(block) + (2 if current else 0)
        if current and current_len + extra > max_chars:
            chunks.append("\n\n".join(current))
            current, current_len = [], 0
        if len(block) > max_chars:
            for idx in range(0, len(block), max_chars):
                if current:
                    chunks.append("\n\n".join(current))
                    current, current_len = [], 0
                chunks.append(block[idx : idx + max_chars])
        else:
            current.append(block)
            current_len += extra
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def send_telegram(message, buttons=None):
    chat_ids = get_telegram_chat_ids()
    if not TELEGRAM_BOT_TOKEN or not chat_ids:
        log("Telegram not configured. Message would be:\n" + message)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    for chat_id in chat_ids:
        for idx, chunk in enumerate(split_telegram_message(message)):
            payload = {
                "chat_id": chat_id,
                "text": chunk,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            }
            if buttons and idx == 0:
                payload["reply_markup"] = {"inline_keyboard": buttons}
            try:
                r = SESSION.post(url, json=payload, timeout=(6, 20))
                if not r.ok:
                    log(f"Telegram response for {chat_id}: HTTP {r.status_code} {r.text[:500]}")
                r.raise_for_status()
                log(f"Telegram sent to {chat_id}")
            except Exception as ex:
                log(f"Telegram error for {chat_id}: {ex}")


def should_send_alert(state, key, cooldown_hours):
    last = state.get("last_alerts", {}).get(key)
    if not last:
        return True
    try:
        return utc_now() - datetime.fromisoformat(last) >= timedelta(hours=float(cooldown_hours))
    except Exception:
        return True


def mark_alert_sent(state, key):
    state.setdefault("last_alerts", {})[key] = iso_now()


def yahoo_symbol(symbol):
    symbol = str(symbol).strip()
    return symbol[:-3].upper() if symbol.lower().endswith(".us") else symbol.upper()


def yahoo_history(symbol, config=None, range_days="6mo"):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol(symbol)}"
    params = {
        "range": range_days,
        "interval": "1d",
        "includePrePost": "false",
        "events": "div,splits",
    }
    try:
        data = request_json(
            url,
            config=config,
            params=params,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
            retries=0,
            read_timeout=10,
        )
        result = (data.get("chart", {}).get("result") or [None])[0]
        if not result:
            return None
        quote = (result.get("indicators", {}).get("quote") or [{}])[0]
        df = pd.DataFrame(
            {
                "date": pd.to_datetime(result.get("timestamp", []), unit="s", utc=True).date,
                "open": quote.get("open", []),
                "high": quote.get("high", []),
                "low": quote.get("low", []),
                "close": quote.get("close", []),
                "volume": quote.get("volume", []),
            }
        )
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        return df.dropna(subset=["close"]).sort_values("date").reset_index(drop=True)
    except Exception as ex:
        log(f"Yahoo error {symbol}: {ex}")
        return None


def calculate_rsi(series, period=14):
    if series is None or len(series) < period + 2:
        return None
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    rsi = 100 - (100 / (1 + rs))
    value = rsi.iloc[-1]
    return None if pd.isna(value) else float(value)


def market_metrics(symbol, config=None, range_days="6mo"):
    df = yahoo_history(symbol, config=config, range_days=range_days)
    if df is None or len(df) < 25:
        return {"symbol": symbol, "status": "unavailable"}
    close = df["close"]
    price = float(close.iloc[-1])
    volume = safe_float(df["volume"].iloc[-1])
    vol20 = safe_float(df["volume"].tail(20).mean())
    high20 = safe_float(df["high"].tail(20).max())
    high50 = safe_float(df["high"].tail(50).max()) if len(df) >= 50 else None
    sma20 = safe_float(close.tail(20).mean())
    sma50 = safe_float(close.tail(50).mean()) if len(df) >= 50 else None
    return {
        "symbol": symbol,
        "status": "ok",
        "price": price,
        "volume": volume,
        "volume_20d_avg": vol20,
        "volume_ratio": volume / vol20 if volume and vol20 else None,
        "rsi": calculate_rsi(close),
        "sma20": sma20,
        "sma50": sma50,
        "perf_5d": pct_change(price, float(close.iloc[-6])) if len(close) > 6 else None,
        "perf_20d": pct_change(price, float(close.iloc[-21])) if len(close) > 21 else None,
        "perf_60d": pct_change(price, float(close.iloc[-61])) if len(close) > 61 else None,
        "breakout_20d": bool(high20 and price >= high20 * 0.995),
        "breakout_50d": bool(high50 and price >= high50 * 0.995),
    }


def ai_summary(agent_name, events, config):
    ai = config.get("ai", {})
    if not ai.get("enabled", True):
        return None
    if not GITHUB_MODELS_TOKEN:
        log("IA omitida: falta GITHUB_TOKEN")
        return None
    selected = [
        {
            "title": e.get("title"),
            "asset": e.get("asset"),
            "score": e.get("score"),
            "level": e.get("level"),
            "summary": e.get("summary"),
            "metrics": e.get("metrics", {}),
            "reasons": e.get("reasons", [])[:5],
        }
        for e in events[: int(ai.get("max_events", 8))]
    ]
    prompt = f"""
Analiza estos eventos de investigacion automatizada para {agent_name}.
Devuelve SOLO JSON valido con:
{{
  "brief": "maximo 3 frases en espanol, profesional y accionable",
  "watch_items": ["punto de vigilancia 1", "punto de vigilancia 2", "punto de vigilancia 3"],
  "risk_notes": ["riesgo 1", "riesgo 2"]
}}
Reglas: no digas compra ahora, vende, garantizado ni senal segura. Usa lenguaje de vigilancia y control de riesgo.
Eventos:
{json.dumps(selected, ensure_ascii=False, indent=2)}
""".strip()
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {GITHUB_MODELS_TOKEN}",
        "X-GitHub-Api-Version": "2026-03-10",
        "Content-Type": "application/json",
    }
    body = {
        "model": ai.get("model", "openai/gpt-4.1-mini"),
        "messages": [
            {"role": "system", "content": "Eres un analista de mercado prudente. Usa solo el JSON recibido y responde siempre en castellano."},
            {"role": "user", "content": prompt},
        ],
        "temperature": float(ai.get("temperature", 0.15)),
        "max_tokens": int(ai.get("max_output_tokens", 700)),
    }
    try:
        r = SESSION.post(
            GITHUB_MODELS_ENDPOINT,
            headers=headers,
            json=body,
            timeout=(6, float(ai.get("timeout_seconds", 45))),
        )
        r.raise_for_status()
        text = r.json()["choices"][0]["message"]["content"].strip()
        text = re.sub(r"^```json\s*", "", text)
        text = re.sub(r"^```\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        match = re.search(r"\{.*\}", text, flags=re.S)
        return json.loads(match.group(0) if match else text)
    except Exception as ex:
        log(f"Error de resumen IA: {ex}")
        return None


def make_event(agent_key, title, asset, score, summary, reasons=None, metrics=None, source=None):
    score = int(round(clamp(score)))
    return {
        "agent": agent_key,
        "time_utc": iso_now(),
        "title": title,
        "asset": asset,
        "score": score,
        "level": score_level(score),
        "summary": summary,
        "reasons": reasons or [],
        "metrics": metrics or {},
        "source": source,
    }


def parse_form4_details(text):
    if not text:
        return {"purchase_count": 0, "sale_count": 0, "shares": 0.0, "avg_price": None}
    codes = re.findall(r"<transactionCode>\s*([A-Z])\s*</transactionCode>", text, flags=re.I)
    shares = [safe_float(x, 0) for x in re.findall(r"<transactionShares>.*?<value>\s*([0-9.,]+)\s*</value>", text, flags=re.I | re.S)]
    prices = [safe_float(x, 0) for x in re.findall(r"<transactionPricePerShare>.*?<value>\s*([0-9.,]+)\s*</value>", text, flags=re.I | re.S)]
    purchases = len([x for x in codes if x.upper() == "P"])
    sales = len([x for x in codes if x.upper() == "S"])
    return {
        "purchase_count": purchases,
        "sale_count": sales,
        "shares": sum(x for x in shares if x),
        "avg_price": sum(prices) / len(prices) if prices else None,
    }


def sec_filings(config):
    events = []
    sec_cfg = config.get("sec", {})
    forms = set(str(x) for x in sec_cfg.get("forms", ["4", "8-K", "10-Q", "10-K", "13D", "13G", "13F-HR"]))
    lookback_days = int(sec_cfg.get("lookback_days", 14))
    max_companies = int(sec_cfg.get("max_companies_per_run", 12))
    headers = {
        "User-Agent": os.getenv("SEC_USER_AGENT") or sec_cfg.get("user_agent", "market-signal-agent contact@example.com"),
        "Accept-Encoding": "gzip, deflate",
    }
    since = utc_now().date() - timedelta(days=lookback_days)
    form4_detail_fetches = 0
    max_form4_detail_fetches = int(sec_cfg.get("max_form4_detail_fetches", 5))
    for company in config.get("companies", [])[:max_companies]:
        cik = str(company.get("cik", "")).zfill(10)
        ticker = company.get("ticker")
        if not cik or not ticker:
            continue
        try:
            data = request_json(f"https://data.sec.gov/submissions/CIK{cik}.json", config, headers=headers, retries=1)
            recent = data.get("filings", {}).get("recent", {})
            metric = market_metrics(ticker, config=config)
            for idx, form in enumerate(recent.get("form", [])[:80]):
                filing_date = recent.get("filingDate", [""])[idx]
                try:
                    filing_day = datetime.strptime(filing_date, "%Y-%m-%d").date()
                except Exception:
                    continue
                if filing_day < since or str(form) not in forms:
                    continue
                accession = recent.get("accessionNumber", [""])[idx]
                primary_doc = recent.get("primaryDocument", [""])[idx]
                base = "https://www.sec.gov/Archives/edgar/data"
                accession_clean = accession.replace("-", "")
                source = f"{base}/{int(cik)}/{accession_clean}/{primary_doc}" if accession and primary_doc else None
                score = 45
                reasons = [f"formulario SEC {form}", f"presentado {filing_date}"]
                form4_details = {}
                if form == "4":
                    score += 25
                    reasons.append("operacion declarada por insider")
                    if sec_cfg.get("parse_form4_details", True) and source and form4_detail_fetches < max_form4_detail_fetches:
                        try:
                            form4_details = parse_form4_details(request_text(source, config, headers=headers, retries=0, read_timeout=10))
                            form4_detail_fetches += 1
                            if form4_details.get("purchase_count"):
                                score += 15
                                reasons.append(f"compras de insiders: {form4_details['purchase_count']}")
                            if form4_details.get("sale_count"):
                                score += 8
                                reasons.append(f"ventas de insiders: {form4_details['sale_count']}")
                        except Exception as ex:
                            log(f"Analisis de detalle Form 4 omitido para {ticker}: {ex}")
                elif form == "8-K":
                    score += 22
                    reasons.append("hecho relevante comunicado")
                elif form in ["13D", "13G"]:
                    score += 20
                    reasons.append("cambio de participacion accionarial")
                elif form == "13F-HR":
                    score += 12
                    reasons.append("actualizacion de posiciones institucionales")
                if safe_float(metric.get("perf_5d"), 0) > 5:
                    score += 8
                    reasons.append("precio reaccionando recientemente")
                events.append(
                    make_event(
                        "sec_filing",
                        f"{ticker} presentacion SEC {form}",
                        ticker,
                        score,
                        f"{company.get('name', ticker)} publico el formulario {form}. Vigilar detalles del documento y reaccion del precio.",
                        reasons,
                        {"filing_date": filing_date, "form": form, "form4_details": form4_details, **metric},
                        source,
                    )
                )
        except Exception as ex:
            log(f"SEC error {ticker}: {ex}")
        time.sleep(float(sec_cfg.get("request_delay_seconds", 0.25)))
    return events


def macro_regime(config):
    proxies = config.get("proxies", {})
    metrics = {name: market_metrics(symbol, config=config) for name, symbol in proxies.items()}
    spy20 = safe_float(metrics.get("SPY", {}).get("perf_20d"), 0)
    qqq20 = safe_float(metrics.get("QQQ", {}).get("perf_20d"), 0)
    hyg20 = safe_float(metrics.get("HYG", {}).get("perf_20d"), 0)
    tlt20 = safe_float(metrics.get("TLT", {}).get("perf_20d"), 0)
    gld20 = safe_float(metrics.get("GLD", {}).get("perf_20d"), 0)
    uup20 = safe_float(metrics.get("UUP", {}).get("perf_20d"), 0)
    risk_score = 50 + spy20 * 3 + qqq20 * 2 + hyg20 * 2 - max(tlt20, 0) - max(gld20, 0) - max(uup20, 0)
    if spy20 > 3 and qqq20 > spy20 and hyg20 > 0:
        regime = "risk-on"
    elif spy20 < -4 or hyg20 < -2:
        regime = "risk-off"
    elif tlt20 > 3 or gld20 > 3:
        regime = "defensive"
    elif spy20 > 0 and gld20 > 0 and uup20 < 0:
        regime = "reflation"
    else:
        regime = "mixed"
    reasons = [
        f"SPY 20D {fmt_pct(spy20)}",
        f"QQQ 20D {fmt_pct(qqq20)}",
        f"HYG 20D {fmt_pct(hyg20)}",
        f"TLT 20D {fmt_pct(tlt20)}",
    ]
    return [
        make_event(
            "macro_regime",
            f"Regimen macro: {regime}",
            "MARKET",
            risk_score,
            f"La cesta de proxies apunta a un regimen {regime}. Vigilar confirmacion en credito, duracion y dolar.",
            reasons,
            {"regime": regime, "proxies": metrics},
            "https://finance.yahoo.com",
        )
    ]


def sector_rotation(config):
    tickers = config.get("tickers", [])
    spy = market_metrics("SPY", config=config)
    spy20 = safe_float(spy.get("perf_20d"), 0)
    events = []
    for item in tickers:
        symbol = item["symbol"] if isinstance(item, dict) else item
        label = item.get("name", symbol) if isinstance(item, dict) else symbol
        m = market_metrics(symbol, config=config)
        if m.get("status") != "ok":
            continue
        rel20 = safe_float(m.get("perf_20d"), 0) - spy20
        score = 50 + rel20 * 4 + safe_float(m.get("perf_5d"), 0) * 2
        if m.get("breakout_20d"):
            score += 10
        if safe_float(m.get("rsi"), 50) > 70:
            score -= 6
        reasons = [
            f"20D {fmt_pct(m.get('perf_20d'))}",
            f"relativo vs SPY {fmt_pct(rel20)}",
            f"RSI {fmt_float(m.get('rsi'), 1)}",
        ]
        events.append(
            make_event(
                "sector_rotation",
                f"{symbol} rotacion sectorial",
                symbol,
                score,
                f"{label} muestra fuerza o debilidad relativa frente a SPY. Vigilar si la rotacion persiste.",
                reasons,
                {**m, "relative_20d_vs_spy": rel20},
                f"https://finance.yahoo.com/quote/{quote_plus(symbol)}",
            )
        )
    return sorted(events, key=lambda x: x["score"], reverse=True)


def defi_liquidity(config):
    events = []
    try:
        chains = request_json("https://api.llama.fi/v2/chains", config, retries=1)
    except Exception as ex:
        log(f"DefiLlama chains error: {ex}")
        chains = []
    wanted = {x.lower(): x for x in config.get("chains", [])}
    for chain in chains:
        name = str(chain.get("name", ""))
        if name.lower() not in wanted:
            continue
        tvl = safe_float(chain.get("tvl"), 0)
        change_1d = safe_float(chain.get("change_1d"), 0)
        change_7d = safe_float(chain.get("change_7d"), 0)
        score = 50 + change_7d * 2 + change_1d
        if tvl > 5_000_000_000:
            score += 8
        reasons = [f"TVL ${tvl:,.0f}", f"1D {fmt_pct(change_1d)}", f"7D {fmt_pct(change_7d)}"]
        events.append(
            make_event(
                "defi_liquidity",
                f"{name} liquidez DeFi",
                name,
                score,
                f"Tendencia de liquidez de {name} segun DefiLlama. Vigilar TVL y confirmacion de actividad en la red.",
                reasons,
                {"tvl": tvl, "change_1d": change_1d, "change_7d": change_7d},
                "https://defillama.com/chains",
            )
        )
    return sorted(events, key=lambda x: x["score"], reverse=True)


def earnings_catalyst(config):
    events = []
    today = utc_now().date()
    lookahead = int(config.get("earnings", {}).get("lookahead_days", 21))
    for item in config.get("companies", []):
        symbol = item.get("ticker")
        date_raw = item.get("earnings_date")
        if not symbol or not date_raw:
            continue
        try:
            earnings_date = datetime.strptime(str(date_raw), "%Y-%m-%d").date()
        except Exception:
            continue
        days = (earnings_date - today).days
        if days < -2 or days > lookahead:
            continue
        m = market_metrics(symbol, config=config)
        score = 45
        reasons = [f"resultados en {days} dias"]
        if 0 <= days <= 10:
            score += 20
        if abs(safe_float(m.get("perf_5d"), 0)) >= 4:
            score += 10
            reasons.append(f"movimiento 5D {fmt_pct(m.get('perf_5d'))}")
        if safe_float(m.get("volume_ratio"), 0) >= 1.5:
            score += 10
            reasons.append(f"volumen {fmt_float(m.get('volume_ratio'), 1)}x")
        if 45 <= safe_float(m.get("rsi"), 50) <= 68:
            score += 6
        events.append(
            make_event(
                "earnings_catalyst",
                f"{symbol} vigilancia de resultados",
                symbol,
                score,
                f"{item.get('name', symbol)} tiene resultados cerca. Es una alerta de vigilancia, no una recomendacion de compra o venta.",
                reasons,
                {**m, "earnings_date": str(earnings_date), "days_until": days},
                f"https://finance.yahoo.com/quote/{quote_plus(symbol)}/analysis",
            )
        )
    return sorted(events, key=lambda x: x["score"], reverse=True)


def cftc_positioning(config):
    events = []
    cftc = config.get("cftc", {})
    url = cftc.get("legacy_csv_url", "https://www.cftc.gov/dea/newcot/deafut.txt")
    try:
        text = request_text(url, config, retries=1, read_timeout=18)
    except Exception as ex:
        log(f"Error al obtener CFTC: {ex}")
        text = ""
    lower = text.lower()
    for market in cftc.get("markets", []):
        name = market.get("name")
        patterns = [p.lower() for p in market.get("match", [])]
        matched = any(p in lower for p in patterns)
        score = 68 if matched else 35
        reasons = ["informe publico CFTC revisado"] + (["mercado encontrado en el informe"] if matched else ["mercado no encontrado; revisar mapeo de config"])
        events.append(
            make_event(
                "cftc_positioning",
                f"{name} posicionamiento CFTC",
                market.get("symbol", name),
                score,
                f"Conviene revisar el posicionamiento de {name} para extremos y cambios semanales.",
                reasons,
                {"matched_public_report": matched, "report_url": url},
                url,
            )
        )
    return sorted(events, key=lambda x: x["score"], reverse=True)


def unusual_volume(config):
    events = []
    uv = config.get("unusual_volume", {})
    min_ratio = float(uv.get("min_volume_ratio", 2.0))
    for item in config.get("watchlist", []):
        symbol = item["symbol"] if isinstance(item, dict) else item
        name = item.get("name", symbol) if isinstance(item, dict) else symbol
        m = market_metrics(symbol, config=config)
        if m.get("status") != "ok":
            continue
        ratio = safe_float(m.get("volume_ratio"), 0)
        score = 45 + max(0, ratio - 1) * 18 + abs(safe_float(m.get("perf_5d"), 0)) * 1.5
        reasons = [f"volume {fmt_float(ratio, 1)}x avg", f"5D {fmt_pct(m.get('perf_5d'))}"]
        if m.get("breakout_20d"):
            score += 12
            reasons.append("cerca de ruptura 20D")
        if m.get("breakout_50d"):
            score += 10
            reasons.append("cerca de ruptura 50D")
        if ratio < min_ratio and not m.get("breakout_20d"):
            score = min(score, 62)
        events.append(
            make_event(
                "unusual_volume",
                f"{symbol} volumen inusual",
                symbol,
                score,
                f"{name} presenta volumen anormal o movimiento tecnico a vigilar.",
                reasons,
                m,
                f"https://finance.yahoo.com/quote/{quote_plus(symbol)}",
            )
        )
    return sorted(events, key=lambda x: x["score"], reverse=True)


def altcoin_fundamentals(config):
    coins = config.get("coins", [])
    ids = ",".join([c["coingecko_id"] for c in coins if c.get("coingecko_id")])
    market_by_id = {}
    if ids:
        try:
            data = request_json(
                "https://api.coingecko.com/api/v3/coins/markets",
                config,
                params={
                    "vs_currency": "usd",
                    "ids": ids,
                    "order": "market_cap_desc",
                    "per_page": len(coins),
                    "page": 1,
                    "price_change_percentage": "24h,7d,30d",
                },
                headers={"User-Agent": "market-signal-agent/1.0", "Accept": "application/json"},
                retries=1,
                read_timeout=14,
            )
            market_by_id = {x.get("id"): x for x in data}
        except Exception as ex:
            log(f"CoinGecko error: {ex}")
    protocols = []
    try:
        protocols = request_json("https://api.llama.fi/protocols", config, retries=1, read_timeout=18)
    except Exception as ex:
        log(f"DefiLlama protocols error: {ex}")
    protocol_by_name = {str(p.get("name", "")).lower(): p for p in protocols}
    events = []
    for coin in coins:
        cg = market_by_id.get(coin.get("coingecko_id"), {})
        proto = protocol_by_name.get(str(coin.get("defillama_name", "")).lower(), {})
        change_7d = safe_float(cg.get("price_change_percentage_7d_in_currency"), 0)
        change_30d = safe_float(cg.get("price_change_percentage_30d_in_currency"), 0)
        volume = safe_float(cg.get("total_volume"), 0)
        market_cap = safe_float(cg.get("market_cap"), 0)
        tvl = safe_float(proto.get("tvl"), 0)
        score = 45 + change_7d * 1.2 + change_30d * 0.25
        if volume and market_cap and volume / market_cap > 0.06:
            score += 10
        if tvl > 1_000_000_000:
            score += 10
        reasons = [
            f"7D {fmt_pct(change_7d)}",
            f"30D {fmt_pct(change_30d)}",
            f"TVL ${tvl:,.0f}" if tvl else "TVL no disponible",
        ]
        events.append(
            make_event(
                "altcoin_fundamentals",
                f"{coin.get('symbol')} vigilancia fundamental",
                coin.get("symbol"),
                score,
                f"{coin.get('name')} muestra metricas publicas de mercado y fundamentales a vigilar. Se excluyen senales tipo memecoin.",
                reasons,
                {"market_cap": market_cap, "volume": volume, "tvl": tvl, "change_7d": change_7d, "change_30d": change_30d},
                f"https://www.coingecko.com/en/coins/{coin.get('coingecko_id')}",
            )
        )
    return sorted(events, key=lambda x: x["score"], reverse=True)


COLLECTORS = {
    "sec_filing": sec_filings,
    "macro_regime": macro_regime,
    "sector_rotation": sector_rotation,
    "defi_liquidity": defi_liquidity,
    "earnings_catalyst": earnings_catalyst,
    "cftc_positioning": cftc_positioning,
    "unusual_volume": unusual_volume,
    "altcoin_fundamentals": altcoin_fundamentals,
}


class PremiumResearchAgent:
    def __init__(self, config_file, agent_key):
        self.config_file = config_file
        self.config = load_yaml(config_file)
        self.agent = self.config.get("agent", {})
        self.agent_key = agent_key or self.agent.get("key")
        self.name = self.agent.get("name", self.agent_key)
        self.state_file = Path(self.agent.get("state_file", f"{self.agent_key}_state.json"))
        self.snapshot_file = Path(self.agent.get("snapshot_file", f"{self.agent_key}_snapshot.json"))
        self.log_file = Path(self.agent.get("log_file", f"{self.agent_key}_log.csv"))
        self.dashboard_file = Path(self.agent.get("dashboard_file", f"docs/{self.agent_key}_dashboard.html"))

    def collect(self):
        collector = COLLECTORS.get(self.agent_key)
        if not collector:
            raise RuntimeError(f"No hay collector registrado para {self.agent_key}")
        try:
            return collector(self.config)
        except Exception as ex:
            log(f"Error fatal del collector del agente: {ex}")
            return [
                make_event(
                    self.agent_key,
                    f"{self.name} degradacion de fuentes",
                    self.agent_key,
                    20,
                    "Fallo la recopilacion principal de datos. Panel y estado se actualizaron igualmente.",
                    [str(ex)[:200]],
                    {"error": str(ex)[:500]},
                )
            ]

    def add_ai(self, events):
        events = sorted(events, key=lambda x: x.get("score", 0), reverse=True)
        brief = ai_summary(self.name, events, self.config)
        if brief:
            for event in events[: int(self.config.get("ai", {}).get("max_events", 8))]:
                event["ai_brief"] = brief.get("brief")
                event["ai_watch_items"] = brief.get("watch_items", [])
                event["ai_risk_notes"] = brief.get("risk_notes", [])
        return events, brief

    def render_dashboard(self, events, ai_brief=None):
        self.dashboard_file.parent.mkdir(parents=True, exist_ok=True)
        events = sorted(events, key=lambda x: x.get("score", 0), reverse=True)
        high = len([x for x in events if x.get("score", 0) >= 80])
        medium = len([x for x in events if 65 <= x.get("score", 0) < 80])
        rows = []
        for event in events[:80]:
            reasons = "; ".join(str(x) for x in event.get("reasons", [])[:4])
            source = event.get("source")
            source_html = f'<a href="{esc(source)}">fuente</a>' if source else "N/A"
            rows.append(
                f"""<tr>
          <td><div class="company">{esc(event.get('asset'))}</div><div class="muted">{esc(event.get('title'))}</div></td>
          <td><span class="pill {'hot' if event.get('score', 0) >= 80 else 'watch' if event.get('score', 0) >= 65 else 'quiet'}">{esc(event.get('score'))}/100</span></td>
          <td>{esc(event.get('level'))}</td>
          <td>{esc(event.get('summary'))}<div class="reason">{esc(reasons)}</div></td>
          <td>{source_html}</td>
        </tr>"""
            )
        ai_html = ""
        if ai_brief:
            watch = "; ".join(ai_brief.get("watch_items", [])[:4])
            risks = "; ".join(ai_brief.get("risk_notes", [])[:3])
            ai_html = f"""<div class="card span-12">
      <h2>Resumen IA</h2>
      <p>{esc(ai_brief.get('brief'))}</p>
      <div class="submetric">Vigilar: {esc(watch or 'N/A')}</div>
      <div class="submetric">Riesgos: {esc(risks or 'N/A')}</div>
    </div>"""
        body = f"""<div class="shell">
  <div class="topbar">
    <div>
      <h1>{esc(self.name)}</h1>
      <div class="muted">Investigacion automatizada premium. Solo datos publicos. No es asesoramiento financiero personalizado.</div>
    </div>
    <nav class="nav">
      <a class="btn" href="index.html">Resumen</a>
      <a class="btn" href="https://github.com/DiegoSR-git/market-signal-agent/actions">Actions</a>
    </nav>
  </div>
  <section class="grid">
    <div class="card span-3"><h3>Eventos</h3><div class="metric">{len(events)}</div><div class="submetric">analizados en la ultima ejecucion</div></div>
    <div class="card span-3"><h3>Alto</h3><div class="metric">{high}</div><div class="submetric">score >= 80</div></div>
    <div class="card span-3"><h3>Medio</h3><div class="metric">{medium}</div><div class="submetric">score 65-79</div></div>
    <div class="card span-3"><h3>Actualizado</h3><div class="metric" style="font-size:20px">{utc_now().strftime('%Y-%m-%d %H:%M UTC')}</div><div class="submetric">UTC</div></div>
    {ai_html}
    <div class="card span-12">
      <h2>Ranking</h2>
      <div class="table-wrap"><table><thead><tr><th>Activo</th><th>Score</th><th>Nivel</th><th>Lectura</th><th>Fuente</th></tr></thead><tbody>{''.join(rows) if rows else '<tr><td colspan="5">Sin datos</td></tr>'}</tbody></table></div>
    </div>
  </section>
  <footer>Generado: {utc_now().strftime('%Y-%m-%d %H:%M UTC')}. Fuente: {esc(self.config_file)}.</footer>
</div>"""
        self.dashboard_file.write_text(render_page(self.name, body), encoding="utf-8")
        try:
            render_home_dashboard("docs/index.html")
        except Exception as ex:
            log(f"Actualizacion del panel principal omitida: {ex}")

    def append_logs(self, events):
        fields = ["time_utc", "agent", "asset", "score", "level", "title", "summary"]
        for event in events:
            append_csv(
                self.log_file,
                fields,
                {
                    "time_utc": utc_now().strftime("%Y-%m-%d %H:%M:%S"),
                    "agent": self.agent_key,
                    "asset": event.get("asset"),
                    "score": event.get("score"),
                    "level": event.get("level"),
                    "title": event.get("title"),
                    "summary": event.get("summary"),
                },
            )

    def build_message(self, events, force=False):
        alerts = self.config.get("alerts", {})
        threshold = int(alerts.get("min_score_to_alert", 75))
        max_alerts = int(alerts.get("max_alerts", 5))
        selected = [x for x in events if x.get("score", 0) >= threshold]
        if force and not selected:
            selected = events[:max_alerts]
        selected = selected[:max_alerts]
        if not selected:
            return None, None
        lines = [
            f"<b>{esc(self.name)}</b>",
            f"<b>Hora:</b> {utc_now().strftime('%Y-%m-%d %H:%M UTC')}",
            f"<b>Eventos:</b> {len(selected)}",
            "",
        ]
        for event in selected:
            reasons = "; ".join(event.get("reasons", [])[:3]) or "N/A"
            lines.extend(
                [
                    f"<b>{esc(event.get('asset'))} - {esc(event.get('title'))}</b>",
                    f"Score: <b>{event.get('score')}/100</b> ({esc(event.get('level'))})",
                    f"Lectura: {esc(event.get('summary'))}",
                    f"Motivos: {esc(reasons)}",
                    "",
                ]
            )
        lines.append("Investigacion automatizada con datos publicos. No es asesoramiento financiero personalizado.")
        buttons = []
        first_source = selected[0].get("source")
        if first_source:
            buttons.append([{"text": "Fuente principal", "url": first_source}])
        buttons.append([{"text": "Panel", "url": f"https://diegosr-git.github.io/market-signal-agent/{self.dashboard_file.name}"}])
        return "\n".join(lines).strip(), buttons

    def run(self, force=False, dry_run=False):
        state = load_state(self.state_file)
        events = self.collect()
        events, brief = self.add_ai(events)
        write_json(self.snapshot_file, events)
        self.append_logs(events)
        self.render_dashboard(events, brief)
        message, buttons = self.build_message(events, force=force)
        if not message:
            log(f"No hay alertas de {self.name} por encima del umbral.")
            save_state(self.state_file, state)
            return events
        alerts = self.config.get("alerts", {})
        cooldown = float(alerts.get("cooldown_hours", 12))
        signature = "|".join(f"{x.get('asset')}:{x.get('score')}:{x.get('title')}" for x in events[:5])
        key = f"{self.agent_key}::{signature}"
        if dry_run:
            log("Prueba en seco activada. El mensaje seria:\n" + message)
        elif force or should_send_alert(state, key, cooldown):
            send_telegram(message, buttons=buttons)
            mark_alert_sent(state, key)
        else:
            log(f"Suprimido por cooldown: {key}")
        save_state(self.state_file, state)
        return events


def main(config_file, agent_key):
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    PremiumResearchAgent(config_file, agent_key).run(force=args.force, dry_run=args.dry_run)
