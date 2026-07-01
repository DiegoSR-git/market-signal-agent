#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
EVENT RUMOR AGENT — FREE

Monitoriza eventos corporativos tech, rumores públicos y ventanas "buy the rumor".
Fuentes gratuitas: Google News RSS (best effort), GDELT DOC API, Yahoo Finance chart API, GitHub Models.
No ejecuta compras ni usa información privada.
"""

import os, re, csv, json, html, time, yaml, argparse, requests
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timezone, timedelta
from urllib.parse import quote_plus
from email.utils import parsedate_to_datetime
import pandas as pd

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
TELEGRAM_CHAT_IDS = os.getenv("TELEGRAM_CHAT_IDS")
GITHUB_MODELS_TOKEN = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
GITHUB_MODELS_ENDPOINT = os.getenv("GITHUB_MODELS_ENDPOINT", "https://models.github.ai/inference/chat/completions")

CONFIG_FILE = os.getenv("EVENT_CONFIG_FILE", "config_events.yaml")
STATE_FILE = Path(os.getenv("EVENT_STATE_FILE", "event_rumor_state.json"))
SNAPSHOT_FILE = Path(os.getenv("EVENT_SNAPSHOT_FILE", "event_rumor_snapshot.json"))
LOG_FILE = Path(os.getenv("EVENT_LOG_FILE", "event_rumor_log.csv"))
DOCS_DIR = Path(os.getenv("EVENT_DOCS_DIR", "docs"))
DASHBOARD_FILE = DOCS_DIR / "event_rumor_dashboard.html"
HTTP_TIMEOUT = 25

def utc_now(): return datetime.now(timezone.utc)
def iso_now(): return utc_now().isoformat()
def e(x): return html.escape(str(x))
def safe_float(x, default=None):
    try: return float(x) if x is not None else default
    except Exception: return default
def parse_iso_date(value):
    if not value: return None
    value = str(value).strip()
    for fmt in ["%Y-%m-%d", "%d %b %Y", "%d %B %Y", "%b %d, %Y", "%B %d, %Y"]:
        try: return datetime.strptime(value, fmt).date()
        except Exception: pass
    try: return datetime.fromisoformat(value.replace("Z","+00:00")).date()
    except Exception: return None
def days_until(date_str):
    d = parse_iso_date(date_str)
    return None if not d else (d - utc_now().date()).days
def fmt_date(v):
    d = parse_iso_date(v)
    return d.isoformat() if d else "N/A"
def fmt_pct(x, decimals=1): return "N/A" if x is None else f"{x:+.{decimals}f}%"
def fmt_float(x, decimals=2): return "N/A" if x is None else f"{x:.{decimals}f}"

def request_json(url, params=None, headers=None, timeout=HTTP_TIMEOUT):
    headers = headers or {"User-Agent":"event-rumor-agent/1.0"}
    r = requests.get(url, params=params, headers=headers, timeout=timeout)
    print(f"HTTP {r.status_code} {r.url[:160]}")
    r.raise_for_status()
    return r.json()
def request_text(url, params=None, headers=None, timeout=HTTP_TIMEOUT):
    headers = headers or {"User-Agent":"Mozilla/5.0"}
    r = requests.get(url, params=params, headers=headers, timeout=timeout)
    print(f"HTTP {r.status_code} {r.url[:160]}")
    r.raise_for_status()
    return r.text

def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f: return yaml.safe_load(f)
def load_state():
    if not STATE_FILE.exists(): return {"last_alerts":{}, "last_run_utc":None}
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        data.setdefault("last_alerts", {})
        return data
    except Exception:
        return {"last_alerts":{}, "last_run_utc":None}
def save_state(state):
    state["last_run_utc"] = iso_now()
    STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")
def should_send_alert(state, key, cooldown_hours):
    last = state.get("last_alerts",{}).get(key)
    if not last: return True
    try: return utc_now() - datetime.fromisoformat(last) >= timedelta(hours=cooldown_hours)
    except Exception: return True
def mark_alert_sent(state, key): state.setdefault("last_alerts", {})[key] = iso_now()

def get_telegram_chat_ids():
    ids = []
    if TELEGRAM_CHAT_IDS: ids.extend(x.strip() for x in TELEGRAM_CHAT_IDS.split(",") if x.strip())
    if TELEGRAM_CHAT_ID: ids.append(TELEGRAM_CHAT_ID.strip())
    out = []
    for x in ids:
        if x not in out: out.append(x)
    return out
def send_telegram(message, buttons=None):
    ids = get_telegram_chat_ids()
    if not TELEGRAM_BOT_TOKEN or not ids:
        print("Telegram not configured. Message would be:\n", message)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    for chat_id in ids:
        payload = {"chat_id":chat_id, "text":message, "parse_mode":"HTML", "disable_web_page_preview":True}
        if buttons:
            payload["reply_markup"] = {"inline_keyboard":[[{"text":b["text"], "url":b["url"]} for b in row] for row in buttons]}
        try:
            r = requests.post(url, json=payload, timeout=HTTP_TIMEOUT); r.raise_for_status()
            print(f"Telegram sent to {chat_id}")
        except Exception as ex:
            print(f"Telegram error for {chat_id}: {ex}")

def append_log(row):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    fields = ["time_utc","ticker","company","score","event_name","event_date","days_until_event","status","summary"]
    exists = LOG_FILE.exists()
    with LOG_FILE.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if not exists: w.writeheader()
        w.writerow({k:row.get(k,"") for k in fields})

def yahoo_symbol(symbol):
    s = symbol.strip()
    return s[:-3].upper() if s.lower().endswith(".us") else s.upper()
def get_yahoo_history(symbol, range_days="6mo"):
    yf = yahoo_symbol(symbol)
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yf}"
    params = {"range":range_days,"interval":"1d","includePrePost":"false","events":"div,splits"}
    try:
        data = request_json(url, params=params, headers={"User-Agent":"Mozilla/5.0","Accept":"application/json"})
        result = data.get("chart",{}).get("result")
        if not result: raise RuntimeError(f"No Yahoo result for {symbol}")
        result = result[0]
        ts = result.get("timestamp", [])
        closes = result.get("indicators",{}).get("quote",[{}])[0].get("close", [])
        df = pd.DataFrame({"date":pd.to_datetime(ts, unit="s", utc=True).date, "close":closes})
        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        return df.dropna(subset=["close"]).sort_values("date").reset_index(drop=True)
    except Exception as ex:
        print(f"Yahoo error {symbol}: {ex}")
        return None
def calculate_rsi(series, period=14):
    if series is None or len(series) < period+2: return None
    delta = series.diff()
    gain, loss = delta.clip(lower=0), -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    rsi = 100 - (100/(1+rs))
    val = rsi.iloc[-1]
    return None if pd.isna(val) else float(val)
def sma(series, period):
    if series is None or len(series) < period: return None
    val = series.rolling(period).mean().iloc[-1]
    return None if pd.isna(val) else float(val)
def pct_change(current, previous):
    if current is None or previous in [None, 0]: return None
    return (current/previous-1)*100
def market_snapshot(ticker):
    df = get_yahoo_history(ticker)
    if df is None or len(df) < 40:
        return {"ticker":ticker,"price":None,"rsi":None,"perf_20d":None,"perf_60d":None,"sma20":None,"sma50":None,"status":"unavailable"}
    close = df["close"]; price = float(close.iloc[-1])
    return {
        "ticker":ticker, "price":price, "rsi":calculate_rsi(close), "sma20":sma(close,20), "sma50":sma(close,50),
        "perf_20d": pct_change(price, float(close.iloc[-21])) if len(close)>21 else None,
        "perf_60d": pct_change(price, float(close.iloc[-61])) if len(close)>61 else None,
        "status":"ok",
    }

def clean_text(x):
    return re.sub(r"\s+"," ",str(x or "")).strip()[:500]
def article_key(a): return a.get("url") or (a.get("title","")+a.get("source",""))
def dedupe_articles(articles):
    seen, out = set(), []
    for a in articles:
        k = article_key(a)
        if k and k not in seen:
            seen.add(k); out.append(a)
    return out

def google_news_rss(query, max_items=10):
    url = "https://news.google.com/rss/search"
    params = {"q":query, "hl":"en-US", "gl":"US", "ceid":"US:en"}
    try:
        xml = request_text(url, params=params)
        root = ET.fromstring(xml)
        items = []
        for item in root.findall(".//item")[:max_items]:
            title = clean_text(item.findtext("title"))
            link = item.findtext("link") or ""
            pub = item.findtext("pubDate")
            source_el = item.find("source")
            source = source_el.text if source_el is not None else "Google News"
            pub_iso = None
            if pub:
                try: pub_iso = parsedate_to_datetime(pub).astimezone(timezone.utc).isoformat()
                except Exception: pub_iso = pub
            items.append({"title":title,"url":link,"published":pub_iso,"source":source,"domain":source,"origin":"google_news_rss","snippet":title})
        return items
    except Exception as ex:
        print(f"Google RSS error {query}: {ex}")
        return []

def gdelt_search(query, max_items=10, timespan="30d"):
    url = "https://api.gdeltproject.org/api/v2/doc/doc"
    params = {"query":query, "mode":"ArtList", "format":"json", "maxrecords":max_items, "timespan":timespan, "sort":"HybridRel"}
    try:
        data = request_json(url, params=params)
        out = []
        for a in data.get("articles", [])[:max_items]:
            out.append({
                "title":clean_text(a.get("title")), "url":a.get("url"), "published":a.get("seendate"),
                "source":a.get("sourceCountry") or a.get("domain") or "GDELT", "domain":a.get("domain"),
                "origin":"gdelt", "snippet":clean_text(a.get("title"))
            })
        return out
    except Exception as ex:
        print(f"GDELT error {query}: {ex}")
        return []

def build_queries(company):
    name, ticker = company["name"], company["ticker"]
    queries, seen = [], set()
    for term in company.get("event_keywords", [])[:5]:
        queries += [f'"{term}" "{name}" 2026 date developer conference product event',
                    f'"{term}" "{ticker}" rumors AI product launch']
    for term in company.get("product_keywords", [])[:8]:
        queries += [f'"{name}" "{term}" rumor launch event 2026',
                    f'"{ticker}" "{term}" analyst expectations']
    queries += [f'"{name}" developer conference 2026 rumors Bloomberg The Verge analyst',
                f'"{name}" product event AI rumors stock expectations']
    out = []
    for q in queries:
        if q not in seen: seen.add(q); out.append(q)
    return out

def fetch_company_news(company, config):
    ncfg = config.get("news", {})
    max_articles = int(ncfg.get("max_articles_per_company", 30))
    max_per_query = int(ncfg.get("max_articles_per_query", 5))
    timespan = ncfg.get("gdelt_timespan", "30d")
    articles = []
    for q in build_queries(company):
        if ncfg.get("use_google_news_rss", True): articles.extend(google_news_rss(q, max_items=max_per_query))
        if ncfg.get("use_gdelt", True): articles.extend(gdelt_search(q, max_items=max_per_query, timespan=timespan))
        articles = dedupe_articles(articles)
        if len(articles) >= max_articles: break
        time.sleep(0.25)
    return dedupe_articles(articles)[:max_articles]

def count_keyword_hits(articles, keywords):
    text = " ".join((a.get("title","")+" "+a.get("snippet","")) for a in articles).lower()
    return [kw for kw in keywords if kw.lower() in text]
def trusted_source_count(articles, trusted_domains):
    count, matched = 0, []
    for a in articles:
        hay = " ".join([str(a.get("url","")), str(a.get("source","")), str(a.get("domain",""))]).lower()
        for d in trusted_domains:
            if d.lower() in hay:
                count += 1; matched.append(d); break
    return count, sorted(set(matched))
def fallback_event_score(company, articles, market, ai_result=None):
    score, reasons = 0, []
    score += min(20, len(articles)*2)
    if articles: reasons.append(f"{len(articles)} artículos recientes")
    tc, tm = trusted_source_count(articles, company.get("trusted_domains", []))
    score += min(20, tc*8)
    if tc: reasons.append(f"Fuentes confiables: {', '.join(tm[:4])}")
    product_hits = count_keyword_hits(articles, company.get("product_keywords", []))
    event_hits = count_keyword_hits(articles, company.get("event_keywords", []))
    score += min(20, len(product_hits)*4)
    if product_hits: reasons.append(f"Rumores/productos: {', '.join(product_hits[:5])}")
    score += min(10, len(event_hits)*3)
    if event_hits: reasons.append(f"Evento mencionado: {', '.join(event_hits[:3])}")
    event_date = (ai_result or {}).get("event_date")
    d = days_until(event_date)
    if d is not None:
        if 0 <= d <= 21: score += 25; reasons.append(f"Dentro de ventana buy-the-rumor: {d} días")
        elif 22 <= d <= 45: score += 15; reasons.append(f"Evento cercano: {d} días")
        elif 46 <= d <= 90: score += 6; reasons.append(f"Evento a medio plazo: {d} días")
    rsi, perf20 = market.get("rsi"), market.get("perf_20d")
    if rsi is not None:
        if 40 <= rsi <= 65: score += 8; reasons.append(f"RSI razonable: {rsi:.1f}")
        elif rsi > 75: score -= 12; reasons.append(f"RSI extendido: {rsi:.1f}")
    if perf20 is not None:
        if perf20 < 3: score += 7; reasons.append(f"No descontado 20D: {perf20:+.1f}%")
        elif perf20 > 12: score -= 10; reasons.append(f"Movimiento 20D avanzado: {perf20:+.1f}%")
    return max(0, min(100, int(round(score)))), reasons

def json_safe(obj):
    if isinstance(obj, pd.DataFrame): return f"<dataframe rows={len(obj)}>"
    if isinstance(obj, pd.Series): return obj.tail(10).tolist()
    if isinstance(obj, dict): return {str(k):json_safe(v) for k,v in obj.items()}
    if isinstance(obj, list): return [json_safe(x) for x in obj[:20]]
    if isinstance(obj, tuple): return [json_safe(x) for x in obj[:20]]
    if isinstance(obj, (str,int,float,bool)) or obj is None: return obj
    try: return float(obj)
    except Exception: return str(obj)
def compact_articles(articles, max_items=12):
    return [{"id":i+1,"title":a.get("title"),"source":a.get("source"),"domain":a.get("domain"),"published":a.get("published"),"url":a.get("url")} for i,a in enumerate(articles[:max_items])]
def build_ai_payload(companies_data):
    return {"as_of_utc":iso_now(), "companies":[{
        "company":x["company"], "ticker":x["ticker"], "market":x["market"],
        "articles":compact_articles(x["articles"]), "manual_event_hint":x["company_config"].get("manual_event_hint"),
        "event_keywords":x["company_config"].get("event_keywords", []),
        "product_keywords":x["company_config"].get("product_keywords", [])
    } for x in companies_data]}

def call_github_models(prompt, config):
    ai = config.get("ai", {})
    if not ai.get("enabled", True): raise RuntimeError("AI disabled")
    if not GITHUB_MODELS_TOKEN: raise RuntimeError("Missing GITHUB_TOKEN")
    headers = {"Accept":"application/vnd.github+json","Authorization":f"Bearer {GITHUB_MODELS_TOKEN}","X-GitHub-Api-Version":"2026-03-10","Content-Type":"application/json"}
    body = {
        "model": ai.get("model","openai/gpt-4.1-mini"),
        "messages": [
            {"role":"system", "content":"Eres un analista financiero cuantitativo. Usa solo el JSON. No inventes fechas ni rumores."},
            {"role":"user", "content":prompt}
        ],
        "temperature": float(ai.get("temperature",0.15)),
        "max_tokens": int(ai.get("max_output_tokens",2200)),
    }
    r = requests.post(GITHUB_MODELS_ENDPOINT, headers=headers, json=body, timeout=60)
    r.raise_for_status()
    text = r.json()["choices"][0]["message"]["content"].strip()
    text = re.sub(r"^```json\s*","",text); text = re.sub(r"^```\s*","",text); text = re.sub(r"\s*```$","",text)
    return json.loads(text)

def ai_analyze(companies_data, config):
    payload = build_ai_payload(companies_data)
    prompt = f"""
Analiza este JSON para detectar oportunidades públicas "buy the rumor" alrededor de eventos corporativos.

Devuelve SOLO JSON válido:
{{
  "companies": [
    {{
      "ticker": "META",
      "company": "Meta Platforms",
      "event_name": "Meta Connect 2026",
      "event_date": "YYYY-MM-DD or null",
      "date_confidence": "confirmed|estimated|rumored|unknown",
      "rumors": ["rumor concreto 1", "rumor concreto 2"],
      "market_sentiment": "skeptical|mixed|priced_in|unknown",
      "trading_window_start": "YYYY-MM-DD or null",
      "trading_window_end": "YYYY-MM-DD or null",
      "window_status": "inside_window|before_window|after_event|unknown",
      "summary": "máximo 2 frases, directo y accionable",
      "sources_used": [1, 2, 3],
      "ai_confidence": "low|medium|high"
    }}
  ]
}}

Reglas:
- No inventes fechas. Si no hay fecha en titulares/fuentes, usa null o manual_event_hint si existe.
- Si usas manual_event_hint, date_confidence="estimated" salvo confirmación en fuentes.
- trading_window_start = event_date - 21 días.
- trading_window_end = event_date.
- Rumores concretos: producto, IA, hardware, software, modelo, partner, guidance.
- No recomiendes compra directa; describe vigilancia y ventana.
- Español.

JSON de entrada:
{json.dumps(json_safe(payload), ensure_ascii=False, indent=2)}
""".strip()
    try: return call_github_models(prompt, config)
    except Exception as ex:
        print(f"AI analyze error: {ex}")
        return {"companies":[]}

def merge_ai_results(companies_data, ai_output):
    ai_by_ticker = {str(x.get("ticker","")).upper():x for x in ai_output.get("companies", []) if x.get("ticker")}
    results = []
    for item in companies_data:
        ticker = item["ticker"]; company = item["company"]; ai = ai_by_ticker.get(ticker, {})
        score, reasons = fallback_event_score(item["company_config"], item["articles"], item["market"], ai)
        if ai.get("ai_confidence") == "high": score += 5
        elif ai.get("ai_confidence") == "low": score -= 5
        score = max(0, min(100, score))
        results.append({
            "ticker":ticker, "company":company, "score":score,
            "event_name": ai.get("event_name") or item["company_config"].get("manual_event_hint",{}).get("name") or "N/A",
            "event_date": ai.get("event_date"), "date_confidence":ai.get("date_confidence","unknown"),
            "days_until_event": days_until(ai.get("event_date")), "trading_window_start":ai.get("trading_window_start"),
            "trading_window_end":ai.get("trading_window_end"), "window_status":ai.get("window_status","unknown"),
            "rumors":ai.get("rumors", []), "market_sentiment":ai.get("market_sentiment","unknown"),
            "summary":ai.get("summary") or "Sin resumen IA concluyente.", "ai_confidence":ai.get("ai_confidence","low"),
            "score_reasons":reasons, "market":item["market"], "articles":item["articles"]
        })
    return sorted(results, key=lambda x:x["score"], reverse=True)

def result_buttons(result):
    buttons = []
    if result.get("articles") and result["articles"][0].get("url"):
        buttons.append([{"text":f"Fuente {result['ticker']}", "url":result["articles"][0]["url"]}])
    buttons.append([
        {"text":f"Yahoo {result['ticker']}", "url":f"https://finance.yahoo.com/quote/{result['ticker']}"},
        {"text":f"Google News {result['ticker']}", "url":f"https://news.google.com/search?q={quote_plus(result['company'])}"}
    ])
    return buttons

def build_message(results, config, force=False):
    acfg = config.get("alerts", {})
    threshold = int(acfg.get("min_score_to_alert",70)); max_alerts = int(acfg.get("max_alerts",5))
    top = [r for r in results if r["score"] >= threshold]
    top = (results[:max_alerts] if force and not top else top[:max_alerts])
    if not top: return None, []
    lines = ["<b>🕵️ EVENT RUMOR WATCH</b>", f"<b>Hora:</b> {utc_now().strftime('%Y-%m-%d %H:%M UTC')}", ""]
    for r in top:
        m = r.get("market", {}); rumors = "; ".join(r.get("rumors", [])[:3]) or "Sin rumores concretos extraídos"
        lines += [
            f"<b>{e(r['ticker'])} — {e(r['company'])}</b>",
            f"Score: <b>{r['score']}/100</b>",
            f"Evento: {e(r['event_name'])}",
            f"Fecha: {e(fmt_date(r['event_date']))} ({e(r['date_confidence'])})",
            f"Días al evento: {e(r['days_until_event'])}",
            f"Ventana 3 semanas: {e(fmt_date(r['trading_window_start']))} → {e(fmt_date(r['trading_window_end']))}",
            f"Estado ventana: {e(r['window_status'])}",
            f"Sentimiento: {e(r['market_sentiment'])}",
            f"Precio: {fmt_float(m.get('price'),2)} | RSI: {fmt_float(m.get('rsi'),1)} | 20D: {fmt_pct(m.get('perf_20d'))}",
            f"Rumores: {e(rumors)}",
            f"Resumen: {e(r['summary'])}",
            ""
        ]
    return "\n".join(lines).strip(), result_buttons(top[0])

def generate_dashboard(results):
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for r in results:
        m = r.get("market", {}); rumors = "; ".join(r.get("rumors", [])[:3])
        rows.append(f"<tr><td>{e(r['ticker'])}</td><td>{e(r['company'])}</td><td>{r['score']}</td><td>{e(r['event_name'])}</td><td>{e(fmt_date(r['event_date']))}</td><td>{e(r['days_until_event'])}</td><td>{e(r['window_status'])}</td><td>{fmt_float(m.get('price'),2)}</td><td>{fmt_float(m.get('rsi'),1)}</td><td>{fmt_pct(m.get('perf_20d'))}</td><td>{e(rumors)}</td></tr>")
    html_doc = f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Event Rumor Watch</title><meta name="viewport" content="width=device-width, initial-scale=1"><style>body{{font-family:system-ui;margin:28px;background:#0b0f19;color:#e5e7eb}}table{{width:100%;border-collapse:collapse}}th,td{{border-bottom:1px solid #273449;padding:10px;text-align:left;vertical-align:top}}th{{background:#111827}}.card{{background:#111827;border:1px solid #273449;border-radius:14px;padding:18px}}</style></head><body><h1>Event Rumor Watch</h1><p>Actualizado: {e(utc_now().strftime('%Y-%m-%d %H:%M UTC'))}</p><div class="card">Monitor de eventos corporativos, filtraciones públicas y ventanas buy-the-rumor.</div><table><thead><tr><th>Ticker</th><th>Empresa</th><th>Score</th><th>Evento</th><th>Fecha</th><th>Días</th><th>Ventana</th><th>Precio</th><th>RSI</th><th>20D</th><th>Rumores</th></tr></thead><tbody>{''.join(rows) if rows else '<tr><td colspan="11">Sin datos</td></tr>'}</tbody></table></body></html>"""
    DASHBOARD_FILE.write_text(html_doc, encoding="utf-8")

def collect_all(config):
    data = []
    for company in config.get("companies", []):
        ticker = company["ticker"].upper(); name = company["name"]
        print(f"\n=== Collecting {ticker} / {name} ===")
        data.append({"ticker":ticker, "company":name, "company_config":company, "market":market_snapshot(ticker), "articles":fetch_company_news(company, config)})
    return data

def run(config, state, force=False):
    companies_data = collect_all(config)
    results = merge_ai_results(companies_data, ai_analyze(companies_data, config))
    SNAPSHOT_FILE.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    generate_dashboard(results)
    for r in results:
        append_log({"time_utc":utc_now().strftime("%Y-%m-%d %H:%M:%S"), "ticker":r["ticker"], "company":r["company"], "score":r["score"], "event_name":r["event_name"], "event_date":fmt_date(r["event_date"]), "days_until_event":r["days_until_event"], "status":r["window_status"], "summary":r["summary"]})
    message, buttons = build_message(results, config, force=force)
    if not message:
        print("No event rumor alerts above threshold.")
        return results
    acfg = config.get("alerts", {}); cooldown = int(acfg.get("cooldown_hours",12)); threshold = int(acfg.get("min_score_to_alert",70))
    top_keys = [f"{r['ticker']}:{r.get('event_date')}:{r['score']}" for r in results if r["score"] >= threshold]
    key = "event_rumor::" + "|".join(top_keys[:5])
    if force or should_send_alert(state, key, cooldown):
        send_telegram(message, buttons=buttons); mark_alert_sent(state, key)
    else:
        print(f"Suppressed by cooldown: {key}")
    return results

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    config = load_config(); state = load_state()
    try: run(config, state, force=args.force)
    finally: save_state(state)

if __name__ == "__main__":
    main()
