#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MARKET SIGNAL AGENT PRO FREE

Gratis:
- BTC/EUR: CoinGecko -> Coinbase -> Kraken
- BTC técnico: RSI, SMA20/50/200, drawdowns, volatilidad realizada
- Derivados: Binance funding + open interest
- Sentimiento: Fear & Greed
- On-chain gratis parcial: CoinMetrics MVRV current ratio si disponible
- ETF flows: variables manuales GitHub o Farside local/self-hosted
- Macro y bolsa: Yahoo Finance chart API + fallback Stooq
- Telegram con botones, anti-spam, state.json, dashboard, daily/weekly/health/backtest
"""

import os
import re
import csv
import json
import html
import math
import time
import yaml
import argparse
from io import StringIO
from pathlib import Path
from datetime import datetime, timezone, timedelta

import requests
import pandas as pd
from bs4 import BeautifulSoup
from dashboard_utils import render_home_dashboard

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
TELEGRAM_CHAT_IDS = os.getenv("TELEGRAM_CHAT_IDS")

ETF_DATE_ENV = os.getenv("ETF_DATE")
ETF_TOTAL_MUSD_ENV = os.getenv("ETF_TOTAL_MUSD")
ETF_IBIT_MUSD_ENV = os.getenv("ETF_IBIT_MUSD")

CONFIG_FILE = os.getenv("CONFIG_FILE", "config.yaml")
STATE_FILE = Path(os.getenv("STATE_FILE", "state.json"))
REPORT_DIR = Path(os.getenv("REPORT_DIR", "docs"))
DASHBOARD_FILE = REPORT_DIR / "dashboard.html"
INDEX_FILE = REPORT_DIR / "index.html"
SIGNAL_LOG_FILE = Path(os.getenv("SIGNAL_LOG_FILE", "signals_log.csv"))
HTTP_TIMEOUT = 25


def utc_now():
    return datetime.now(timezone.utc)


def iso_now():
    return utc_now().isoformat()


def e(x):
    return html.escape(str(x))


def safe_float(value, default=None):
    try:
        if value is None or (isinstance(value, str) and value.strip() == ""):
            return default
        return float(value)
    except Exception:
        return default


def parse_number(x):
    if x is None:
        return 0.0
    s = str(x).strip()
    if s in ["-", "", "nan", "None", "N/A"]:
        return 0.0
    negative = s.startswith("(") and s.endswith(")")
    s = s.replace("(", "").replace(")", "").replace(",", "").replace("$", "").replace("M", "").replace("%", "").replace("−", "-").strip()
    try:
        value = float(s)
        return -value if negative else value
    except ValueError:
        return 0.0


def pct_change(current, previous):
    if current is None or previous in [None, 0]:
        return None
    return (current / previous - 1) * 100


def clamp(value, lo=0, hi=100):
    return max(lo, min(hi, value))


def fmt_eur(v, decimals=0):
    return "N/A" if v is None else f"{v:,.{decimals}f} €"


def fmt_pct(v, decimals=1, signed=True):
    if v is None:
        return "N/A"
    return f"{v:{'+' if signed else ''}.{decimals}f}%"


def fmt_musd(v):
    return "N/A" if v is None else f"{v:+.1f} M$"


def fmt_float(v, decimals=2):
    return "N/A" if v is None else f"{v:.{decimals}f}"


def request_json(url, params=None, headers=None):
    r = requests.get(url, params=params, headers=headers or {"User-Agent": "market-signal-agent/2.0"}, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    return r.json()


def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_state():
    if not STATE_FILE.exists():
        return {"last_alerts": {}, "orders": {}, "last_snapshot": {}, "last_run_utc": None}
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        state = {}
    state.setdefault("last_alerts", {})
    state.setdefault("orders", {})
    state.setdefault("last_snapshot", {})
    return state


def save_state(state):
    state["last_run_utc"] = iso_now()
    STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def should_send_alert(state, key, cooldown_hours):
    last = state.get("last_alerts", {}).get(key)
    if not last:
        return True
    try:
        return utc_now() - datetime.fromisoformat(last) >= timedelta(hours=cooldown_hours)
    except Exception:
        return True


def mark_alert_sent(state, key):
    state.setdefault("last_alerts", {})[key] = iso_now()


def append_signal_log(row):
    SIGNAL_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["time_utc", "asset", "signal_type", "score", "price", "status", "details"]
    file_exists = SIGNAL_LOG_FILE.exists()
    with SIGNAL_LOG_FILE.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow({k: row.get(k, "") for k in fieldnames})


def get_telegram_chat_ids():
    """
    Soporta:
    - TELEGRAM_CHAT_ID: un solo chat principal
    - TELEGRAM_CHAT_IDS: varios chats separados por coma

    Ejemplo:
      TELEGRAM_CHAT_IDS = 123456789,987654321,555444333
    """
    chat_ids = []

    if TELEGRAM_CHAT_IDS:
        chat_ids.extend(
            x.strip()
            for x in TELEGRAM_CHAT_IDS.split(",")
            if x.strip()
        )

    if TELEGRAM_CHAT_ID:
        chat_ids.append(TELEGRAM_CHAT_ID.strip())

    # Quitar duplicados preservando orden
    unique = []
    for chat_id in chat_ids:
        if chat_id not in unique:
            unique.append(chat_id)

    return unique


def send_telegram(message, buttons=None):
    chat_ids = get_telegram_chat_ids()

    if not TELEGRAM_BOT_TOKEN or not chat_ids:
        print("Telegram secrets missing. Message would be:")
        print(message)
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    for chat_id in chat_ids:
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }

        if buttons:
            payload["reply_markup"] = {
                "inline_keyboard": [
                    [{"text": b["text"], "url": b["url"]} for b in row]
                    for row in buttons
                ]
            }

        try:
            r = requests.post(url, json=payload, timeout=HTTP_TIMEOUT)
            r.raise_for_status()
            print(f"Telegram sent to {chat_id}")
        except Exception as ex:
            # No rompe el envío al resto de chats si uno falla
            print(f"Telegram error for chat_id {chat_id}: {ex}")

def default_buttons():
    return [
        [
            {"text": "BTC CoinGecko", "url": "https://www.coingecko.com/en/coins/bitcoin"},
            {"text": "Farside ETF", "url": "https://farside.co.uk/btc/"},
        ],
        [
            {"text": "Fear & Greed", "url": "https://alternative.me/crypto/fear-and-greed-index/"},
            {"text": "TradingView BTC", "url": "https://www.tradingview.com/symbols/BTCEUR/"},
        ],
    ]


# -----------------------------------------------------------------------------
# Indicators
# -----------------------------------------------------------------------------

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
    latest = rsi.iloc[-1]
    return None if pd.isna(latest) else float(latest)


def calculate_rsi_series(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    return 100 - (100 / (1 + rs))


def sma(series, period):
    if series is None or len(series) < period:
        return None
    v = series.rolling(period).mean().iloc[-1]
    return None if pd.isna(v) else float(v)


def drawdown_from_high(series, lookback):
    if series is None or len(series) < lookback:
        return None
    window = series.tail(lookback)
    high, last = float(window.max()), float(window.iloc[-1])
    return None if high == 0 else (last / high - 1) * 100


def realized_volatility(series, period):
    if series is None or len(series) < period + 2:
        return None
    returns = series.pct_change().dropna()
    vol = returns.tail(period).std() * math.sqrt(365) * 100
    return None if pd.isna(vol) else float(vol)


def distance_to_level(price, level):
    if price is None or level in [None, 0]:
        return None
    return (price / level - 1) * 100


# -----------------------------------------------------------------------------
# BTC / Crypto data
# -----------------------------------------------------------------------------

def get_btc_price_eur():
    errors = []
    try:
        data = request_json("https://api.coingecko.com/api/v3/simple/price", {"ids": "bitcoin", "vs_currencies": "eur"})
        return float(data["bitcoin"]["eur"]), "coingecko"
    except Exception as ex:
        errors.append(f"CoinGecko: {ex}")
    try:
        data = request_json("https://api.coinbase.com/v2/prices/BTC-EUR/spot")
        return float(data["data"]["amount"]), "coinbase"
    except Exception as ex:
        errors.append(f"Coinbase: {ex}")
    try:
        data = request_json("https://api.kraken.com/0/public/Ticker", {"pair": "XBTEUR"})
        result = next(iter(data["result"].values()))
        return float(result["c"][0]), "kraken"
    except Exception as ex:
        errors.append(f"Kraken: {ex}")
    raise RuntimeError("Could not fetch BTC/EUR. " + " | ".join(errors))


def get_btc_daily_prices(days=365):
    """
    CoinGecko public/free puede devolver 401 si pides rangos largos.
    Para producción gratis, limitamos por defecto a 365 días.
    Ajustable con COINGECKO_MAX_DAYS.
    """
    requested_days = int(days)
    max_free_days = int(os.getenv("COINGECKO_MAX_DAYS", "365"))
    effective_days = min(requested_days, max_free_days)

    if requested_days != effective_days:
        print(
            f"CoinGecko free mode: requested {requested_days} days, "
            f"using {effective_days} days to avoid 401."
        )

    data = request_json(
        "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart",
        params={"vs_currency": "eur", "days": effective_days, "interval": "daily"},
    )
    prices = data.get("prices", [])
    if not prices:
        raise RuntimeError("CoinGecko returned no historical prices")

    df = pd.DataFrame(prices, columns=["timestamp", "price"])
    df["date"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True).dt.date
    df = df.drop_duplicates(subset=["date"], keep="last")
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df = df.dropna(subset=["price"])
    return df[["date", "price"]].reset_index(drop=True)


def get_fear_and_greed():
    try:
        data = request_json("https://api.alternative.me/fng/", {"limit": 1})
        item = data["data"][0]
        return {"value": int(item["value"]), "classification": item.get("value_classification", "N/A")}
    except Exception as ex:
        print(f"Fear & Greed error: {ex}")
        return {"value": None, "classification": "N/A", "error": str(ex)}


def get_binance_funding(limit=8):
    """
    Funding BTCUSDT con cadena gratuita de fallback:
    1) Binance Futures
    2) Bybit v5
    3) OKX public

    Binance puede devolver 451 desde GitHub-hosted runners.
    """
    errors = []

    # 1) Binance
    try:
        data = request_json(
            "https://fapi.binance.com/fapi/v1/fundingRate",
            params={"symbol": "BTCUSDT", "limit": limit},
        )
        rates = [float(x["fundingRate"]) for x in data]
        latest = rates[-1] if rates else None
        avg_5 = sum(rates[-5:]) / min(len(rates), 5) if rates else None
        negative_count = sum(1 for r in rates[-5:] if r < 0)
        return {
            "latest": latest,
            "avg_5": avg_5,
            "negative_count_5": negative_count,
            "source": "binance_futures",
        }
    except Exception as ex:
        errors.append(f"Binance funding: {ex}")
        print(f"Binance funding error: {ex}")

    # 2) Bybit
    try:
        data = request_json(
            "https://api.bybit.com/v5/market/funding/history",
            params={"category": "linear", "symbol": "BTCUSDT", "limit": limit},
        )
        rows = data.get("result", {}).get("list", [])
        rows = sorted(rows, key=lambda x: int(x.get("fundingRateTimestamp", 0)))
        rates = [float(x["fundingRate"]) for x in rows if x.get("fundingRate") is not None]
        latest = rates[-1] if rates else None
        avg_5 = sum(rates[-5:]) / min(len(rates), 5) if rates else None
        negative_count = sum(1 for r in rates[-5:] if r < 0)
        return {
            "latest": latest,
            "avg_5": avg_5,
            "negative_count_5": negative_count,
            "source": "bybit",
        }
    except Exception as ex:
        errors.append(f"Bybit funding: {ex}")
        print(f"Bybit funding error: {ex}")

    # 3) OKX
    try:
        data = request_json(
            "https://www.okx.com/api/v5/public/funding-rate-history",
            params={"instId": "BTC-USDT-SWAP", "limit": limit},
        )
        rows = data.get("data", [])
        rows = sorted(rows, key=lambda x: int(x.get("fundingTime", 0)))
        rates = [float(x["fundingRate"]) for x in rows if x.get("fundingRate") is not None]
        latest = rates[-1] if rates else None
        avg_5 = sum(rates[-5:]) / min(len(rates), 5) if rates else None
        negative_count = sum(1 for r in rates[-5:] if r < 0)
        return {
            "latest": latest,
            "avg_5": avg_5,
            "negative_count_5": negative_count,
            "source": "okx",
        }
    except Exception as ex:
        errors.append(f"OKX funding: {ex}")
        print(f"OKX funding error: {ex}")

    return {
        "latest": None,
        "avg_5": None,
        "negative_count_5": None,
        "source": "unavailable",
        "error": " | ".join(errors),
    }

def get_binance_open_interest():
    """
    Open Interest actual con fallback gratuito:
    1) Binance Futures
    2) Bybit v5
    3) OKX public

    Devuelve una cifra comparable dentro de cada fuente, no entre fuentes.
    """
    errors = []

    # 1) Binance
    try:
        data = request_json(
            "https://fapi.binance.com/fapi/v1/openInterest",
            params={"symbol": "BTCUSDT"},
        )
        return {
            "open_interest": float(data.get("openInterest")),
            "time": data.get("time"),
            "source": "binance_futures",
        }
    except Exception as ex:
        errors.append(f"Binance OI current: {ex}")
        print(f"Binance OI current error: {ex}")

    # 2) Bybit current from latest historical OI point
    try:
        data = request_json(
            "https://api.bybit.com/v5/market/open-interest",
            params={
                "category": "linear",
                "symbol": "BTCUSDT",
                "intervalTime": "1h",
                "limit": 2,
            },
        )
        rows = data.get("result", {}).get("list", [])
        rows = sorted(rows, key=lambda x: int(x.get("timestamp", 0)))
        latest = rows[-1]
        return {
            "open_interest": float(latest.get("openInterest")),
            "time": latest.get("timestamp"),
            "source": "bybit",
        }
    except Exception as ex:
        errors.append(f"Bybit OI current: {ex}")
        print(f"Bybit OI current error: {ex}")

    # 3) OKX current
    try:
        data = request_json(
            "https://www.okx.com/api/v5/public/open-interest",
            params={"instType": "SWAP", "uly": "BTC-USDT"},
        )
        rows = data.get("data", [])
        if not rows:
            raise RuntimeError("OKX returned no OI rows")
        latest = rows[0]
        oi = latest.get("oiCcy") or latest.get("oi")
        return {
            "open_interest": float(oi),
            "time": latest.get("ts"),
            "source": "okx",
        }
    except Exception as ex:
        errors.append(f"OKX OI current: {ex}")
        print(f"OKX OI current error: {ex}")

    return {
        "open_interest": None,
        "source": "unavailable",
        "error": " | ".join(errors),
    }

def get_binance_open_interest_hist(period="1h", limit=30):
    """
    Historical OI con fallback:
    1) Binance Futures
    2) Bybit v5

    OKX se usa solo para OI actual en get_binance_open_interest.
    """
    errors = []

    # 1) Binance
    try:
        data = request_json(
            "https://fapi.binance.com/futures/data/openInterestHist",
            params={"symbol": "BTCUSDT", "period": period, "limit": limit},
        )
        if not data:
            raise RuntimeError("Binance returned no OI history")

        vals = [float(x["sumOpenInterest"]) for x in data]
        latest = vals[-1]
        prev_24 = vals[-25] if len(vals) >= 25 else vals[0]
        prev_recent = vals[-7] if len(vals) >= 7 else vals[0]

        return {
            "latest": latest,
            "change_24h": pct_change(latest, prev_24),
            "change_recent": pct_change(latest, prev_recent),
            "source": "binance_futures",
        }
    except Exception as ex:
        errors.append(f"Binance OI hist: {ex}")
        print(f"Binance OI hist error: {ex}")

    # 2) Bybit
    try:
        data = request_json(
            "https://api.bybit.com/v5/market/open-interest",
            params={
                "category": "linear",
                "symbol": "BTCUSDT",
                "intervalTime": period,
                "limit": limit,
            },
        )
        rows = data.get("result", {}).get("list", [])
        rows = sorted(rows, key=lambda x: int(x.get("timestamp", 0)))
        vals = [float(x["openInterest"]) for x in rows if x.get("openInterest") is not None]

        if not vals:
            raise RuntimeError("Bybit returned no OI history")

        latest = vals[-1]
        prev_24 = vals[-25] if len(vals) >= 25 else vals[0]
        prev_recent = vals[-7] if len(vals) >= 7 else vals[0]

        return {
            "latest": latest,
            "change_24h": pct_change(latest, prev_24),
            "change_recent": pct_change(latest, prev_recent),
            "source": "bybit",
        }
    except Exception as ex:
        errors.append(f"Bybit OI hist: {ex}")
        print(f"Bybit OI hist error: {ex}")

    return {
        "latest": None,
        "change_24h": None,
        "change_recent": None,
        "source": "unavailable",
        "error": " | ".join(errors),
    }

def get_coinmetrics_mvrv():
    for metric in ["CapMVRVCur", "CapMVRVFreeFloat"]:
        try:
            data = request_json(
                "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics",
                {"assets": "btc", "metrics": metric, "frequency": "1d", "page_size": 10, "pretty": "false"},
            )
            rows = [r for r in data.get("data", []) if r.get(metric) is not None]
            if rows:
                latest = rows[-1]
                return {"metric": metric, "value": float(latest[metric]), "time": latest.get("time")}
        except Exception as ex:
            print(f"CoinMetrics {metric} error: {ex}")
    return {"metric": None, "value": None, "time": None}


def etf_stale_days(date_str):
    if not date_str:
        return None
    for fmt in ["%Y-%m-%d", "%d %b %Y", "%d %B %Y"]:
        try:
            return (utc_now().date() - datetime.strptime(date_str, fmt).date()).days
        except Exception:
            pass
    return None


def get_latest_etf_flows():
    manual_total = safe_float(ETF_TOTAL_MUSD_ENV)
    manual_ibit = safe_float(ETF_IBIT_MUSD_ENV)
    if ETF_DATE_ENV and (manual_total is not None or manual_ibit is not None):
        return {"date": ETF_DATE_ENV, "ibit": manual_ibit, "total": manual_total, "source": "manual_env", "available": True, "stale_days": etf_stale_days(ETF_DATE_ENV)}

    urls = ["https://farside.co.uk/btc/", "https://farside.co.uk/bitcoin-etf-flow-all-data/"]
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
    date_regex = re.compile(r"\b\d{1,2} [A-Za-z]{3} \d{4}\b")
    number_regex = re.compile(r"\(?-?\d{1,3}(?:,\d{3})*(?:\.\d+)?\)?|\(?-?\d+(?:\.\d+)?\)?")
    last_error = None

    for url in urls:
        try:
            r = requests.get(url, headers=headers, timeout=HTTP_TIMEOUT)
            print(f"Farside HTTP {r.status_code} from {url}")
            if r.status_code == 403:
                last_error = "Farside 403 Forbidden from this runner/IP"
                continue
            r.raise_for_status()
            text = BeautifulSoup(r.text, "html.parser").get_text(" ")
            text = re.sub(r"\s+", " ", text.replace("\xa0", " "))
            matches = list(date_regex.finditer(text))
            rows = []
            for idx, m in enumerate(matches):
                date = m.group(0)
                block = text[m.end(): matches[idx + 1].start() if idx + 1 < len(matches) else len(text)]
                for stopper in ["Average", "Maximum", "Minimum", "Source:", "All data"]:
                    if stopper in block:
                        block = block.split(stopper)[0]
                nums = number_regex.findall(block)
                if len(nums) >= 13:
                    # Farside BTC common order: Total, IBIT, FBTC, ...
                    rows.append({"date": date, "total": parse_number(nums[0]), "ibit": parse_number(nums[1])})
            if rows:
                latest = rows[-1]
                latest.update({"source": "farside_scrape", "available": True, "stale_days": etf_stale_days(latest["date"])})
                return latest
        except Exception as ex:
            last_error = str(ex)
            print(f"Farside error with {url}: {ex}")

    return {"date": "N/A", "ibit": None, "total": None, "source": "unavailable", "available": False, "stale_days": None, "reason": last_error or "ETF unavailable"}


# -----------------------------------------------------------------------------
# Yahoo / Stooq
# -----------------------------------------------------------------------------

def yahoo_symbol(symbol):
    s = symbol.strip()
    return s[:-3].upper() if s.lower().endswith(".us") else s.upper()


def stooq_symbol(symbol):
    s = symbol.strip().lower()
    return s if "." in s else f"{s}.us"


def get_yahoo_history(symbol, range_days="2y"):
    yf_symbol = yahoo_symbol(symbol)
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yf_symbol}"
    params = {"range": range_days, "interval": "1d", "includePrePost": "false", "events": "div,splits"}
    try:
        r = requests.get(url, params=params, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}, timeout=HTTP_TIMEOUT)
        print(f"Yahoo HTTP {r.status_code} for {symbol} -> {yf_symbol}")
        r.raise_for_status()
        data = r.json()
        result = data.get("chart", {}).get("result")
        if not result:
            raise RuntimeError(f"No Yahoo chart result for {symbol}")
        result = result[0]
        timestamps = result.get("timestamp", [])
        closes = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
        if not timestamps or not closes:
            raise RuntimeError(f"No Yahoo timestamps/closes for {symbol}")
        df = pd.DataFrame({"date": pd.to_datetime(timestamps, unit="s", utc=True).date, "close": closes})
        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        df = df.dropna(subset=["close"]).drop_duplicates("date", keep="last").sort_values("date").reset_index(drop=True)
        if len(df) < 60:
            raise RuntimeError(f"Insufficient Yahoo data for {symbol}: {len(df)} rows")
        return df
    except Exception as ex:
        print(f"Yahoo error for {symbol}: {ex}")
        return None


def get_stooq_history(symbol):
    try:
        r = requests.get("https://stooq.com/q/d/l", params={"s": stooq_symbol(symbol), "i": "d"}, headers={"User-Agent": "Mozilla/5.0"}, timeout=HTTP_TIMEOUT)
        print(f"Stooq HTTP {r.status_code} for {symbol} -> {r.url}")
        r.raise_for_status()
        text = r.text.strip()
        if "No data" in text or len(text) < 50 or "Date,Open,High,Low,Close" not in text:
            raise RuntimeError("No valid Stooq CSV data")
        df = pd.read_csv(StringIO(text))
        df.columns = [c.lower() for c in df.columns]
        df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        return df.dropna(subset=["date", "close"]).drop_duplicates("date", keep="last").sort_values("date").reset_index(drop=True)
    except Exception as ex:
        print(f"Stooq error for {symbol}: {ex}")
        return None


def get_stock_history(symbol):
    df = get_yahoo_history(symbol)
    return df if df is not None else get_stooq_history(symbol)


def macro_snapshot(config):
    if not config.get("macro", {}).get("enabled", True):
        return {}
    out = {}
    for key, symbol in config.get("macro", {}).get("symbols", {}).items():
        df = get_stock_history(symbol)
        if df is None or len(df) < 50:
            out[key] = {"symbol": symbol, "price": None}
            continue
        close = df["close"]
        price = float(close.iloc[-1])
        s20, s50, s200 = sma(close, 20), sma(close, 50), sma(close, 200)
        out[key] = {"symbol": symbol, "price": price, "rsi": calculate_rsi(close), "sma20": s20, "sma50": s50, "sma200": s200, "dist_sma20": distance_to_level(price, s20), "dist_sma200": distance_to_level(price, s200)}
        time.sleep(0.1)
    return out


def infer_market_regime(macro, btc_metrics):
    qqq, spy, vix = macro.get("qqq", {}), macro.get("spy", {}), macro.get("vix", {})
    btc_dist200 = distance_to_level(btc_metrics.get("price"), btc_metrics.get("sma200"))
    risk_on, risk_off = 0, 0
    if qqq.get("dist_sma200") is not None:
        risk_on += 2 if qqq["dist_sma200"] > 0 else 0
        risk_off += 2 if qqq["dist_sma200"] <= 0 else 0
    if spy.get("dist_sma200") is not None:
        risk_on += 1 if spy["dist_sma200"] > 0 else 0
        risk_off += 1 if spy["dist_sma200"] <= 0 else 0
    if vix.get("price") is not None:
        risk_off += 3 if vix["price"] >= 30 else 0
        risk_on += 1 if vix["price"] <= 18 else 0
    if btc_dist200 is not None:
        risk_on += 1 if btc_dist200 > 0 else 0
        risk_off += 1 if btc_dist200 < -10 else 0
    if risk_off >= risk_on + 3:
        return "RISK_OFF"
    if risk_on >= risk_off + 2:
        return "RISK_ON"
    return "NEUTRAL"


# -----------------------------------------------------------------------------
# Orders
# -----------------------------------------------------------------------------

def init_order_state(config, state):
    state.setdefault("orders", {})
    for level in config.get("btc", {}).get("levels", []):
        order_id = level.get("id") or f"btc_{int(level['price_eur'])}"
        state["orders"].setdefault(order_id, {"price_eur": level["price_eur"], "amount_eur": level["amount_eur"], "name": level.get("name", order_id), "first_triggered_utc": None, "last_triggered_utc": None, "times_seen": 0})


def update_order_state(config, state, price):
    init_order_state(config, state)
    touched = []
    for level in config.get("btc", {}).get("levels", []):
        order_id = level.get("id") or f"btc_{int(level['price_eur'])}"
        if price <= float(level["price_eur"]):
            rec = state["orders"][order_id]
            rec["first_triggered_utc"] = rec.get("first_triggered_utc") or iso_now()
            rec["last_triggered_utc"] = iso_now()
            rec["times_seen"] = int(rec.get("times_seen", 0)) + 1
            touched.append({**level, "id": order_id})
    return touched


def orders_summary(config, state):
    init_order_state(config, state)
    lines = []
    for order_id, rec in sorted(state.get("orders", {}).items(), key=lambda x: x[1]["price_eur"], reverse=True):
        status = "tocada" if rec.get("first_triggered_utc") else "pendiente"
        lines.append(f"{order_id}: {fmt_eur(rec['price_eur'])} / {fmt_eur(rec['amount_eur'])} / {status}")
    return lines


# -----------------------------------------------------------------------------
# BTC signal
# -----------------------------------------------------------------------------

def collect_btc_metrics(config):
    price, src = get_btc_price_eur()
    df = get_btc_daily_prices(int(config["btc"].get("history_days", 365)))
    close = df["price"]
    return {
        "price": price, "price_source": src, "price_history": df,
        "rsi_daily": calculate_rsi(close), "sma20": sma(close, 20), "sma50": sma(close, 50), "sma200": sma(close, 200),
        "dd30": drawdown_from_high(close, 30), "dd90": drawdown_from_high(close, 90),
        "vol14": realized_volatility(close, 14), "vol30": realized_volatility(close, 30),
        "etf": get_latest_etf_flows(), "fear": get_fear_and_greed(), "funding": get_binance_funding(),
        "oi_current": get_binance_open_interest(), "oi_hist": get_binance_open_interest_hist(),
        "mvrv": get_coinmetrics_mvrv() if config["btc"].get("enable_mvrv", True) else {"value": None},
    }


def score_btc(config, state, m, macro=None):
    t = config["btc"]["thresholds"]
    price = m["price"]
    score, reasons, actions, blocks, signal_types = 0, [], [], [], []
    touched = update_order_state(config, state, price)

    if touched:
        deepest = touched[-1]
        score += min(35, 15 + 5 * len(touched))
        signal_types.append("BUY_LIMIT_TOUCH")
        reasons.append(f"BTC en zona de órdenes: <= {fmt_eur(deepest['price_eur'])} ({deepest.get('name')})")
        actions += [f"Revisar orden límite: {fmt_eur(o['amount_eur'])} en {fmt_eur(o['price_eur'])}" for o in touched]

    rsi = m["rsi_daily"]
    if rsi is not None:
        if rsi <= float(t["rsi_daily_deep_buy"]):
            score += 25; signal_types.append("CAPITULATION_RSI"); reasons.append(f"RSI diario capitulación: {rsi:.1f}")
        elif rsi <= float(t["rsi_daily_buy"]):
            score += 15; reasons.append(f"RSI diario sobrevendido: {rsi:.1f}")

    reclaim = float(config["btc"]["rebound"]["reclaim_price_eur"])
    if price >= reclaim:
        score += 15; signal_types.append("LUMP_SUM_RECLAIM"); reasons.append(f"Precio recupera reclaim: {fmt_eur(reclaim)}")
        actions.append("Preparar Fase B / Lump Sum reactivo; exigir ETF/funding/macro confirmando.")
        if rsi is not None and rsi >= float(t["rsi_daily_confirm"]):
            score += 10; reasons.append(f"RSI confirma momentum tras reclaim: {rsi:.1f}")

    dist200 = distance_to_level(price, m["sma200"])
    if dist200 is not None:
        if dist200 <= float(t.get("distance_sma200_deep_discount", -20)): score += 12; reasons.append(f"BTC muy bajo SMA200: {dist200:.1f}%")
        elif dist200 <= float(t.get("distance_sma200_discount", -5)): score += 6; reasons.append(f"BTC bajo SMA200: {dist200:.1f}%")
        elif dist200 >= float(t.get("distance_sma200_overheat", 25)): score -= 10; blocks.append(f"BTC muy extendido sobre SMA200: {dist200:.1f}%")

    if m["dd30"] is not None and m["dd30"] <= float(t.get("drawdown_30d_buy_pct", -15)): score += 10; reasons.append(f"Drawdown 30D relevante: {m['dd30']:.1f}%")
    if m["dd90"] is not None and m["dd90"] <= float(t.get("drawdown_90d_buy_pct", -25)): score += 10; reasons.append(f"Drawdown 90D fuerte: {m['dd90']:.1f}%")
    if m["vol14"] and m["vol30"] and m["vol30"] > 0 and m["vol14"] / m["vol30"] >= float(t.get("volatility_spike_ratio", 1.5)):
        score += 8; reasons.append(f"Volatilidad 14D/30D elevada: {m['vol14']/m['vol30']:.2f}x")

    etf_total, ibit = m["etf"].get("total"), m["etf"].get("ibit")
    stale = m["etf"].get("stale_days")
    if stale is not None and stale >= int(t.get("etf_stale_warning_days", 4)): blocks.append(f"ETF desactualizado: {stale} días")
    if etf_total is not None:
        if etf_total >= float(t["etf_total_strong_musd"]): score += 25; reasons.append(f"ETF total fuerte: {fmt_musd(etf_total)}")
        elif etf_total >= float(t["etf_total_green_musd"]): score += 15; reasons.append(f"ETF total positivo: {fmt_musd(etf_total)}")
        elif etf_total <= float(t["etf_block_musd"]): score -= 25; signal_types.append("RISK_BLOCK"); blocks.append(f"ETF total bloquea compras tácticas: {fmt_musd(etf_total)}")
    if ibit is not None:
        if ibit >= float(t["ibit_strong_musd"]): score += 20; reasons.append(f"IBIT fuerte: {fmt_musd(ibit)}")
        elif ibit >= float(t["ibit_green_musd"]): score += 12; reasons.append(f"IBIT positivo relevante: {fmt_musd(ibit)}")
        elif ibit <= float(t["ibit_block_musd"]): score -= 20; signal_types.append("RISK_BLOCK"); blocks.append(f"IBIT bloquea compras tácticas: {fmt_musd(ibit)}")

    fg = m["fear"].get("value")
    if fg is not None:
        if fg <= int(t.get("fear_extreme", 25)): score += 15; reasons.append(f"Fear & Greed extremo: {fg} ({m['fear'].get('classification')})")
        elif fg <= int(t.get("fear_buy", 40)): score += 8; reasons.append(f"Fear & Greed en miedo: {fg} ({m['fear'].get('classification')})")
        elif fg >= int(t.get("greed_block", 75)): score -= 10; signal_types.append("FOMO_WARNING"); blocks.append(f"Sentimiento codicioso: {fg}")

    neg_count = m["funding"].get("negative_count_5")
    avg_funding = m["funding"].get("avg_5")
    oi24 = m["oi_hist"].get("change_24h")
    if neg_count is not None:
        if neg_count >= int(t.get("funding_negative_count_buy", 3)): score += 8; reasons.append(f"Funding negativo {neg_count}/5")
        elif avg_funding is not None and avg_funding > float(t.get("funding_overheated", 0.0002)): score -= 8; blocks.append(f"Funding elevado: avg5={avg_funding:.5f}")
    if oi24 is not None:
        if oi24 <= float(t.get("oi_flush_24h_pct", -8)) and neg_count is not None and neg_count >= 2: score += 12; signal_types.append("LEVERAGE_FLUSH"); reasons.append(f"OI cae {oi24:.1f}% 24h + funding negativo")
        elif oi24 >= float(t.get("oi_overheat_24h_pct", 10)) and avg_funding is not None and avg_funding > 0: score -= 8; blocks.append(f"OI sube {oi24:.1f}% 24h con funding positivo")

    mvrv = m["mvrv"].get("value")
    if mvrv is not None:
        if mvrv <= float(t.get("mvrv_current_deep_buy", 1.05)): score += 18; reasons.append(f"MVRV current muy bajo: {mvrv:.2f}")
        elif mvrv <= float(t.get("mvrv_current_buy", 1.35)): score += 10; reasons.append(f"MVRV current atractivo: {mvrv:.2f}")
        elif mvrv >= float(t.get("mvrv_current_hot", 2.8)): score -= 10; blocks.append(f"MVRV current alto: {mvrv:.2f}")

    regime = infer_market_regime(macro, m) if macro else "N/A"
    if regime == "RISK_ON" and price >= reclaim: score += 8; reasons.append("Macro risk-on acompaña reclaim")
    elif regime == "RISK_OFF": score -= 8; blocks.append("Macro risk-off: reducir agresividad")

    score = int(round(clamp(score, 0, 100)))
    status = "🟢 BTC COMPRA FUERTE" if score >= 85 else "🟠 BTC COMPRA PARCIAL" if score >= 70 else "🟡 BTC EN VIGILANCIA" if score >= 55 else "⚪ SIN SEÑAL"
    if not signal_types: signal_types = ["NO_SIGNAL" if score < 55 else "SCORE_WATCH"]
    return {"score": score, "status": status, "signal_types": sorted(set(signal_types)), "reasons": reasons, "actions": actions, "blocks": blocks, "market_regime": regime, "touched_orders": touched}


def btc_message(config, m, s, macro=None):
    reasons = "\n".join("- " + e(x) for x in s["reasons"]) if s["reasons"] else "- Ninguna señal relevante"
    actions = "\n".join("- " + e(x) for x in s["actions"]) if s["actions"] else "- No comprar; seguir esperando"
    blocks = "\n".join("- " + e(x) for x in s["blocks"]) if s["blocks"] else "- Ninguno"
    macro_lines = []
    if macro:
        for k, v in macro.items():
            if v.get("price") is not None:
                macro_lines.append(f"{k.upper()} {v.get('symbol')}: {v['price']:.2f}, dist200={fmt_pct(v.get('dist_sma200'))}")
    macro_text = "\n".join("- " + e(x) for x in macro_lines[:6]) if macro_lines else "- N/A"
    f = m["funding"]; oi = m["oi_hist"]; oi_cur = m["oi_current"]; etf = m["etf"]; fear = m["fear"]; mvrv = m["mvrv"]

    return f"""
<b>{e(s['status'])}</b>

<b>Signal types:</b> {e(", ".join(s["signal_types"]))}
<b>Score:</b> {s["score"]}/100
<b>Regime:</b> {e(s["market_regime"])}

<b>BTC:</b>
Precio BTC/EUR: {m['price']:,.0f} €
Fuente precio: {e(m['price_source'])}
RSI diario: {fmt_float(m['rsi_daily'], 1)}
SMA20: {fmt_eur(m['sma20'])}
SMA50: {fmt_eur(m['sma50'])}
SMA200: {fmt_eur(m['sma200'])}
Dist. SMA200: {fmt_pct(distance_to_level(m['price'], m['sma200']))}
Drawdown 30D: {fmt_pct(m['dd30'])}
Drawdown 90D: {fmt_pct(m['dd90'])}
Vol 14D: {fmt_pct(m['vol14'], 1, signed=False)}
Vol 30D: {fmt_pct(m['vol30'], 1, signed=False)}

<b>ETF flows:</b>
Fecha: {e(etf.get('date'))}
Fuente: {e(etf.get('source'))}
IBIT: {fmt_musd(etf.get('ibit'))}
Total: {fmt_musd(etf.get('total'))}
Stale days: {e(etf.get('stale_days'))}

<b>Sentimiento / Derivados / On-chain:</b>
Fear & Greed: {e(str(fear.get('value')) + ' / ' + str(fear.get('classification')) if fear.get('value') is not None else 'N/A')}
Funding BTCUSDT: {e(f"latest={f.get('latest'):.5f}, avg5={f.get('avg_5'):.5f}, neg5={f.get('negative_count_5')}" if f.get('latest') is not None and f.get('avg_5') is not None else "N/A")}
Open Interest: {e(f"OI={fmt_float(oi_cur.get('open_interest'), 0)}, 24h={fmt_pct(oi.get('change_24h'))}, recent={fmt_pct(oi.get('change_recent'))}" if oi_cur.get('open_interest') is not None else "N/A")}
MVRV current: {e(f"{mvrv.get('value'):.2f} ({mvrv.get('metric')})" if mvrv.get('value') is not None else "N/A")}

<b>Macro:</b>
{macro_text}

<b>Razones:</b>
{reasons}

<b>Bloqueos/Riesgos:</b>
{blocks}

<b>Acciones sugeridas:</b>
{actions}

<b>Hora:</b> {utc_now().strftime("%Y-%m-%d %H:%M UTC")}
""".strip()


def run_btc_signal(config, state, force=False):
    m = collect_btc_metrics(config)
    macro = macro_snapshot(config)
    s = score_btc(config, state, m, macro)
    msg = btc_message(config, m, s, macro)
    print(msg)

    trigger = f"ORDER_{s['touched_orders'][-1]['price_eur']}" if s["touched_orders"] else s["signal_types"][0]
    alert_key = f"btc::{trigger}::{s['status']}"
    append_signal_log({"time_utc": utc_now().strftime("%Y-%m-%d %H:%M:%S"), "asset": "BTC", "signal_type": trigger, "score": s["score"], "price": m["price"], "status": s["status"], "details": "|".join(s["reasons"][:5])})

    state["last_snapshot"]["btc"] = {
        "time_utc": iso_now(), "price": m["price"], "score": s["score"], "status": s["status"], "regime": s["market_regime"],
        "rsi": m["rsi_daily"], "sma200": m["sma200"], "fear": m["fear"].get("value"), "etf_total": m["etf"].get("total"),
        "ibit": m["etf"].get("ibit"), "oi_24h": m["oi_hist"].get("change_24h"),
    }

    threshold = int(config.get("alerts", {}).get("btc_alert_score", 70))
    cooldown = int(config.get("alerts", {}).get("cooldown_hours", 6))
    if force or s["score"] >= threshold:
        if force or should_send_alert(state, alert_key, cooldown):
            send_telegram(msg, buttons=default_buttons())
            mark_alert_sent(state, alert_key)
        else:
            print(f"Alert suppressed by cooldown: {alert_key}")
    return m, s, macro


# -----------------------------------------------------------------------------
# Stocks
# -----------------------------------------------------------------------------

def scan_stocks(config):
    stock_cfg = config.get("stocks", {})
    if not stock_cfg.get("enabled", False): return []
    th = stock_cfg.get("thresholds", {})
    out = []
    for symbol in stock_cfg.get("watchlist", [])[: int(stock_cfg.get("max_items_per_run", 10))]:
        df = get_stock_history(symbol)
        if df is None or len(df) < 220: continue
        close = df["close"]; last = float(close.iloc[-1])
        rsi = calculate_rsi(close); s20=sma(close,20); s200=sma(close,200); dd=drawdown_from_high(close,252); dist200=distance_to_level(last,s200)
        score, reasons = 0, []
        if dd is not None and dd <= float(th.get("min_drawdown_pct", -10)): score += 25; reasons.append(f"Drawdown 52s {dd:.1f}%")
        if rsi is not None and rsi <= float(th.get("max_rsi_daily", 35)): score += 25; reasons.append(f"RSI diario {rsi:.1f}")
        if s200 is not None and last >= s200: score += 10; reasons.append("Precio sobre SMA200")
        elif s200 is not None and dist200 is not None and -8 <= dist200 <= 0: score += 10; reasons.append("Cerca de SMA200 desde abajo")
        if s20 is not None and last >= s20: score += 15; reasons.append("Recupera SMA20")
        if bool(th.get("require_close_above_sma20", False)) and s20 is not None and last < s20: score -= 20; reasons.append("Aún no recupera SMA20")
        if score >= int(th.get("alert_score", 50)):
            out.append({"symbol": symbol, "price": last, "score": score, "rsi": rsi, "drawdown": dd, "dist200": dist200, "reasons": reasons})
        time.sleep(0.15)
    return sorted(out, key=lambda x: x["score"], reverse=True)


def stock_message(ops):
    if not ops: return None
    lines = []
    for item in ops[:10]:
        lines.append(f"• <b>{e(item['symbol'])}</b> — score {item['score']}, precio {item['price']:.2f}, RSI {fmt_float(item['rsi'], 1)}, DD52s {fmt_pct(item['drawdown'])}, dist200 {fmt_pct(item['dist200'])}\n  {e(', '.join(item['reasons']))}")
    return f"<b>📈 STOCK / ETF WATCHLIST</b>\n\n{chr(10).join(lines)}\n\n<b>Hora:</b> {utc_now().strftime('%Y-%m-%d %H:%M UTC')}"


def run_stock_signal(config, state, force=False):
    ops = scan_stocks(config)
    msg = stock_message(ops)
    state["last_snapshot"]["stocks"] = {"time_utc": iso_now(), "opportunities": len(ops), "top": ops[:5]}
    if not msg:
        print("No stock/ETF opportunities.")
        return ops
    print(msg)
    key = "stocks::opportunities"; cooldown = int(config.get("alerts", {}).get("cooldown_hours", 6))
    if force or should_send_alert(state, key, cooldown):
        send_telegram(msg); mark_alert_sent(state, key)
    return ops


# -----------------------------------------------------------------------------
# Reports / health / dashboard / backtest
# -----------------------------------------------------------------------------

def healthcheck(config):
    checks = []

    def record(name, ok, detail, required=True):
        checks.append(
            {
                "name": name,
                "ok": bool(ok),
                "detail": str(detail),
                "required": bool(required),
            }
        )

    try:
        p, src = get_btc_price_eur()
        record("BTC price", True, f"{p:.0f} EUR via {src}", required=True)
    except Exception as ex:
        record("BTC price", False, str(ex), required=True)

    try:
        df = get_btc_daily_prices(30)
        record("BTC history", len(df) > 10, f"{len(df)} rows", required=True)
    except Exception as ex:
        record("BTC history", False, str(ex), required=True)

    try:
        fg = get_fear_and_greed()
        detail = (
            f"{fg.get('value')} / {fg.get('classification')}"
            if fg.get("value") is not None
            else fg.get("error", "N/A")
        )
        record("Fear & Greed", fg.get("value") is not None, detail, required=True)
    except Exception as ex:
        record("Fear & Greed", False, str(ex), required=True)

    try:
        f = get_binance_funding()
        detail = (
            f"{f.get('source')} latest={fmt_float(f.get('latest'), 6)} "
            f"avg5={fmt_float(f.get('avg_5'), 6)} neg5={f.get('negative_count_5')}"
        )
        record("Derivatives funding", f.get("latest") is not None, detail, required=False)
    except Exception as ex:
        record("Derivatives funding", False, str(ex), required=False)

    try:
        oi = get_binance_open_interest()
        detail = f"{oi.get('source')} OI={fmt_float(oi.get('open_interest'), 0)}"
        record("Derivatives OI", oi.get("open_interest") is not None, detail, required=False)
    except Exception as ex:
        record("Derivatives OI", False, str(ex), required=False)

    try:
        etf = get_latest_etf_flows()
        detail = (
            f"{etf.get('source')} date={etf.get('date')} "
            f"total={fmt_musd(etf.get('total'))} IBIT={fmt_musd(etf.get('ibit'))}"
        )
        # ETF es opcional porque Farside bloquea GitHub Actions. Usa variables manuales si lo quieres OK.
        record("ETF flows", etf.get("available", False), detail, required=False)
    except Exception as ex:
        record("ETF flows", False, str(ex), required=False)

    try:
        macro = macro_snapshot(config)
        ok = any(v.get("price") is not None for v in macro.values())
        detail = ", ".join(
            f"{k}={fmt_float(v.get('price'), 2)}"
            for k, v in macro.items()
            if v.get("price") is not None
        )
        record("Macro Yahoo", ok, detail or "N/A", required=True)
    except Exception as ex:
        record("Macro Yahoo", False, str(ex), required=True)

    required_checks = [c for c in checks if c["required"]]
    optional_checks = [c for c in checks if not c["required"]]

    required_ok = all(c["ok"] for c in required_checks)
    optional_ok = all(c["ok"] for c in optional_checks)

    if required_ok and optional_ok:
        status = "✅ HEALTHCHECK OK"
    elif required_ok and not optional_ok:
        status = "🟡 HEALTHCHECK OK — optional data degraded"
    else:
        status = "⚠️ HEALTHCHECK WARNING"

    lines = []
    for c in checks:
        if c["ok"]:
            icon = "✅"
        elif c["required"]:
            icon = "❌"
        else:
            icon = "⚪"

        label = "" if c["required"] else " (opcional)"
        lines.append(f"{icon} {e(c['name'])}{label}: {e(c['detail'])}")

    return f"""
<b>{status}</b>

{chr(10).join(lines)}

<b>Hora:</b> {utc_now().strftime("%Y-%m-%d %H:%M UTC")}
""".strip()

def run_healthcheck(config, state, force=False):
    msg = healthcheck(config); print(msg)
    if force or config.get("reports", {}).get("send_healthcheck", True): send_telegram(msg)


def daily_report(config, state):
    m = collect_btc_metrics(config); macro=macro_snapshot(config); s=score_btc(config,state,m,macro)
    ops = scan_stocks(config) if config.get("stocks", {}).get("enabled", False) else []
    order_text = "\n".join("- " + e(x) for x in orders_summary(config, state)) or "- N/A"
    stocks_text = "\n".join("- " + e(f"{x['symbol']}: score {x['score']}, RSI {fmt_float(x['rsi'],1)}, DD {fmt_pct(x['drawdown'])}") for x in ops[:5]) or "- Sin oportunidades destacadas"
    conclusion = s["actions"][0] if s["actions"] else "No comprar; seguir esperando"
    return f"""
<b>📊 DAILY MARKET BRIEF</b>

<b>BTC:</b>
Precio: {m['price']:,.0f} €
Score: {s['score']}/100
Estado: {e(s['status'])}
Regime: {e(s['market_regime'])}
RSI: {fmt_float(m['rsi_daily'], 1)}
SMA200: {fmt_eur(m['sma200'])}
Fear & Greed: {e(m['fear'].get('value'))} / {e(m['fear'].get('classification'))}
ETF total: {fmt_musd(m['etf'].get('total'))}
IBIT: {fmt_musd(m['etf'].get('ibit'))}
OI 24h: {fmt_pct(m['oi_hist'].get('change_24h'))}

<b>Órdenes BTC:</b>
{order_text}

<b>Bolsa/ETFs:</b>
{stocks_text}

<b>Conclusión:</b>
{e(conclusion)}

<b>Hora:</b> {utc_now().strftime('%Y-%m-%d %H:%M UTC')}
""".strip()


def run_daily_report(config, state, force=False):
    msg = daily_report(config, state); print(msg)
    if force or config.get("reports", {}).get("send_daily", True): send_telegram(msg, buttons=default_buttons())


def weekly_report(config, state):
    m = collect_btc_metrics(config); macro=macro_snapshot(config); s=score_btc(config,state,m,macro)
    levels = config["btc"].get("crisis_levels", {})
    mode = "CRISIS" if m["price"] <= float(levels.get("crisis_eur", 35200)) else "CAPITULATION" if m["price"] <= float(levels.get("capitulation_eur", 40000)) else "NORMAL"
    return f"""
<b>🧭 WEEKLY REGIME REPORT</b>

<b>BTC regime:</b> {e(s['market_regime'])}
<b>Execution mode:</b> {e(mode)}
<b>Score:</b> {s['score']}/100
<b>Precio:</b> {m['price']:,.0f} €
<b>Distancia SMA200:</b> {fmt_pct(distance_to_level(m['price'], m['sma200']))}
<b>RSI diario:</b> {fmt_float(m['rsi_daily'], 1)}
<b>Drawdown 90D:</b> {fmt_pct(m['dd90'])}
<b>Vol 14D/30D:</b> {fmt_pct(m['vol14'], 1, signed=False)} / {fmt_pct(m['vol30'], 1, signed=False)}
<b>Funding neg5:</b> {e(m['funding'].get('negative_count_5'))}
<b>OI 24h:</b> {fmt_pct(m['oi_hist'].get('change_24h'))}
<b>Fear & Greed:</b> {e(m['fear'].get('value'))} / {e(m['fear'].get('classification'))}
<b>ETF total:</b> {fmt_musd(m['etf'].get('total'))}
<b>IBIT:</b> {fmt_musd(m['etf'].get('ibit'))}

<b>Plan semanal:</b>
- Si BTC toca niveles límite: ejecutar solo tramos definidos.
- Si reclaim > {fmt_eur(config['btc']['rebound']['reclaim_price_eur'])}: exigir confirmación ETF/funding/macro.
- Si modo CRISIS: congelar Lump Sum y exigir estabilización 24–48h.

<b>Hora:</b> {utc_now().strftime('%Y-%m-%d %H:%M UTC')}
""".strip()


def run_weekly_report(config, state, force=False):
    msg = weekly_report(config, state); print(msg)
    if force or config.get("reports", {}).get("send_weekly", True): send_telegram(msg, buttons=default_buttons())


def generate_dashboard(config, state):
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    btc = state.get("last_snapshot", {}).get("btc", {})
    orders = state.get("orders", {})
    order_rows = "".join(
        f"<tr><td>{e(k)}</td><td>{fmt_eur(v.get('price_eur'))}</td><td>{fmt_eur(v.get('amount_eur'))}</td><td>{'Tocada' if v.get('first_triggered_utc') else 'Pendiente'}</td><td>{e(v.get('times_seen'))}</td></tr>"
        for k, v in sorted(orders.items(), key=lambda x: x[1]["price_eur"], reverse=True)
    )
    stock_top = state.get("last_snapshot", {}).get("stocks", {}).get("top", [])
    stock_rows = "".join(
        f"<tr><td>{e(x.get('symbol'))}</td><td>{x.get('score')}</td><td>{fmt_float(x.get('rsi'),1)}</td><td>{fmt_pct(x.get('drawdown'))}</td><td>{fmt_pct(x.get('dist200'))}</td></tr>"
        for x in stock_top
    )
    html_doc = f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Market Signal Agent</title><meta name="viewport" content="width=device-width, initial-scale=1"><style>body{{font-family:system-ui;margin:32px;background:#0b0f19;color:#e5e7eb}}.card{{background:#111827;border:1px solid #273449;border-radius:14px;padding:20px;margin:18px 0}}table{{width:100%;border-collapse:collapse}}td,th{{border-bottom:1px solid #273449;padding:10px;text-align:left}}.score{{font-size:42px;font-weight:800}}.muted{{color:#9ca3af}}</style></head><body>
<h1>Panel Market Signal Agent</h1><p class="muted">Actualizado: {utc_now().strftime("%Y-%m-%d %H:%M UTC")}</p>
<div class="card"><h2>BTC</h2><div class="score">{e(btc.get('score','N/A'))}/100</div><p><b>Estado:</b> {e(btc.get('status','N/A'))}</p><p><b>Precio:</b> {fmt_eur(btc.get('price'))}</p><p><b>Regime:</b> {e(btc.get('regime','N/A'))}</p><p><b>RSI:</b> {fmt_float(btc.get('rsi'),1)} | <b>SMA200:</b> {fmt_eur(btc.get('sma200'))}</p><p><b>Fear:</b> {e(btc.get('fear','N/A'))} | <b>ETF total:</b> {fmt_musd(btc.get('etf_total'))} | <b>IBIT:</b> {fmt_musd(btc.get('ibit'))} | <b>OI 24h:</b> {fmt_pct(btc.get('oi_24h'))}</p></div>
<div class="card"><h2>Órdenes BTC</h2><table><thead><tr><th>ID</th><th>Precio</th><th>Importe</th><th>Estado</th><th>Veces</th></tr></thead><tbody>{order_rows or '<tr><td colspan="5">Sin órdenes</td></tr>'}</tbody></table></div>
<div class="card"><h2>Bolsa / ETFs</h2><table><thead><tr><th>Símbolo</th><th>Score</th><th>RSI</th><th>DD52s</th><th>Dist. SMA200</th></tr></thead><tbody>{stock_rows or '<tr><td colspan="5">Sin oportunidades</td></tr>'}</tbody></table></div>
</body></html>"""
    DASHBOARD_FILE.write_text(html_doc, encoding="utf-8")
    render_home_dashboard(INDEX_FILE)
    print(f"Panel escrito en {DASHBOARD_FILE} y {INDEX_FILE}")


def backtest_btc(config):
    """
    Backtest simple gratuito:
    - Señal RSI < threshold
    - Retornos forward 30D/90D

    Nota: CoinGecko free puede limitar históricos largos. El agente usa
    COINGECKO_MAX_DAYS=365 por defecto para evitar 401.
    """
    btc_cfg = config["btc"]
    threshold = float(btc_cfg["thresholds"].get("rsi_daily_buy", 35))

    requested_days = int(btc_cfg.get("backtest_days", 365))
    max_free_days = int(os.getenv("COINGECKO_MAX_DAYS", "365"))
    effective_days = min(requested_days, max_free_days)

    try:
        df = get_btc_daily_prices(days=effective_days)
    except Exception as ex:
        return f"""
<b>🧪 BTC BACKTEST BASELINE</b>

No disponible ahora.
Motivo: {e(ex)}

El resto del weekly report sigue siendo válido.
Hora: {utc_now().strftime("%Y-%m-%d %H:%M UTC")}
""".strip()

    df["rsi"] = calculate_rsi_series(df["price"], 14)
    df["ret_30d"] = df["price"].shift(-30) / df["price"] - 1
    df["ret_90d"] = df["price"].shift(-90) / df["price"] - 1

    signals = df[df["rsi"] <= threshold].copy()
    signals = signals.dropna(subset=["ret_30d", "ret_90d"])

    if signals.empty:
        return f"""
<b>🧪 BTC BACKTEST BASELINE</b>

Regla: RSI diario <= {threshold:.1f}
Ventana usada: {effective_days} días
Señales evaluables: 0

No hay suficientes señales cerradas con retorno 30D/90D en la ventana gratuita actual.
Hora: {utc_now().strftime("%Y-%m-%d %H:%M UTC")}
""".strip()

    win30 = (signals["ret_30d"] > 0).mean() * 100
    win90 = (signals["ret_90d"] > 0).mean() * 100
    avg30 = signals["ret_30d"].mean() * 100
    avg90 = signals["ret_90d"].mean() * 100
    n = len(signals)

    return f"""
<b>🧪 BTC BACKTEST BASELINE</b>

Regla: RSI diario <= {threshold:.1f}
Ventana usada: {effective_days} días
Señales: {n}
Win rate 30D: {win30:.1f}%
Retorno medio 30D: {avg30:+.1f}%
Win rate 90D: {win90:.1f}%
Retorno medio 90D: {avg90:+.1f}%

Nota: baseline técnico. No incluye ETF, funding, OI ni macro.
Hora: {utc_now().strftime("%Y-%m-%d %H:%M UTC")}
""".strip()


def run_backtest(config, state, force=False):
    msg = backtest_btc(config); print(msg)
    if force or config.get("reports", {}).get("send_backtest", False): send_telegram(msg)



# =============================================================================
# GITHUB MODELS AI SUMMARY
# =============================================================================

GITHUB_MODELS_TOKEN = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
GITHUB_MODELS_ENDPOINT = os.getenv(
    "GITHUB_MODELS_ENDPOINT",
    "https://models.github.ai/inference/chat/completions",
)


def json_safe(obj):
    """
    Convierte objetos no serializables en JSON seguro.
    Evita mandar DataFrames completos a GitHub Models.
    """
    try:
        if isinstance(obj, pd.DataFrame):
            return f"<dataframe rows={len(obj)} cols={list(obj.columns)}>"
        if isinstance(obj, pd.Series):
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
                "content": "Eres un analista cuantitativo. Debes resumir datos de mercado sin inventar información.",
            },
            {
                "role": "user",
                "content": prompt,
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


# Reemplaza btc_message para añadir IA solo si config lo permite.
_original_btc_message = btc_message


def btc_message(config, m, s, macro=None):
    msg = _original_btc_message(config, m, s, macro)

    if config.get("ai_summary", {}).get("send_in_signal_alerts", False):
        ai_text = generate_ai_summary(config, m, s, macro)
        msg += "\n\n<b>🧠 Resumen IA:</b>\n" + e(ai_text)

    return msg


# Reemplaza daily_report para añadir IA en el mensaje diario.
_original_daily_report = daily_report


def daily_report(config, state):
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

    return msg


# Reemplaza weekly_report para añadir IA en el mensaje semanal.
_original_weekly_report = weekly_report


def weekly_report(config, state):
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

    return msg


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["signal","btc","stocks","daily","weekly","health","dashboard","backtest","all"], default="signal")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    config = load_config()
    state = load_state()
    init_order_state(config, state)
    try:
        if args.mode in ["signal","btc","all"] and config.get("btc", {}).get("enabled", False): run_btc_signal(config, state, args.force)
        if args.mode in ["signal","stocks","all"] and config.get("stocks", {}).get("enabled", False): run_stock_signal(config, state, args.force)
        if args.mode == "daily": run_daily_report(config, state, args.force)
        if args.mode == "weekly": run_weekly_report(config, state, args.force)
        if args.mode == "health": run_healthcheck(config, state, args.force)
        if args.mode == "dashboard": generate_dashboard(config, state)
        if args.mode == "backtest": run_backtest(config, state, args.force)
    finally:
        save_state(state)
        try: generate_dashboard(config, state)
        except Exception as ex: print(f"Fallo la generacion del panel: {ex}")


if __name__ == "__main__":
    main()
