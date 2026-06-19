import os
import re
import math
import json
import html
import yaml
import time
import argparse
from pathlib import Path
from datetime import datetime, timezone, timedelta

import requests
import pandas as pd
from bs4 import BeautifulSoup


# =============================================================================
# MARKET SIGNAL AGENT — BTC + ETF manual fallback + sentiment + funding + stocks
# Gratis / sin claves obligatorias:
# - BTC/EUR: CoinGecko + Coinbase/Kraken fallback
# - RSI/SMA/Drawdown: CoinGecko histórico
# - Fear & Greed: Alternative.me
# - Funding BTCUSDT: Binance Futures public endpoint
# - MVRV aproximado: CoinMetrics Community API, si la métrica está disponible
# - ETF flows: Farside si corre local/self-hosted; GitHub Actions suele recibir 403
#              fallback manual por ENV / GitHub Variables
# - Bolsa/ETFs: Stooq CSV sin API key
# - Alertas: Telegram Bot API
# - Anti-spam: state.json con cooldown por señal
# =============================================================================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Manual ETF fallback. Úsalo en GitHub Actions → Settings → Secrets and variables → Actions → Variables
# ETF_DATE="2026-06-18"
# ETF_TOTAL_MUSD="-96.7"
# ETF_IBIT_MUSD="0.0"
ETF_DATE_ENV = os.getenv("ETF_DATE")
ETF_TOTAL_MUSD_ENV = os.getenv("ETF_TOTAL_MUSD")
ETF_IBIT_MUSD_ENV = os.getenv("ETF_IBIT_MUSD")

CONFIG_FILE = os.getenv("CONFIG_FILE", "config.yaml")
STATE_FILE = Path(os.getenv("STATE_FILE", "state.json"))

HTTP_TIMEOUT = 25


def utc_now():
    return datetime.now(timezone.utc)


def safe_float(value, default=None):
    try:
        if value is None:
            return default
        if isinstance(value, str) and value.strip() == "":
            return default
        return float(value)
    except Exception:
        return default


def parse_number(x):
    """
    Convierte formatos tipo:
    "(96.7)" => -96.7
    "1,234.5" => 1234.5
    "-" / "N/A" => 0.0
    """
    if x is None:
        return 0.0

    s = str(x).strip()

    if s in ["-", "", "nan", "None", "N/A"]:
        return 0.0

    negative = s.startswith("(") and s.endswith(")")
    s = (
        s.replace("(", "")
        .replace(")", "")
        .replace(",", "")
        .replace("$", "")
        .replace("M", "")
        .replace("−", "-")
        .strip()
    )

    try:
        value = float(s)
        return -value if negative else value
    except ValueError:
        return 0.0


def request_json(url, params=None, headers=None, timeout=HTTP_TIMEOUT):
    headers = headers or {"User-Agent": "market-signal-agent/1.0"}
    r = requests.get(url, params=params, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r.json()


def request_text(url, params=None, headers=None, timeout=HTTP_TIMEOUT):
    headers = headers or {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        )
    }
    r = requests.get(url, params=params, headers=headers, timeout=timeout)
    print(f"HTTP {r.status_code} from {url}")
    r.raise_for_status()
    return r.text


def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_state():
    if not STATE_FILE.exists():
        return {"last_alerts": {}, "last_run_utc": None}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"last_alerts": {}, "last_run_utc": None}


def save_state(state):
    state["last_run_utc"] = utc_now().isoformat()
    STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def should_send_alert(state, key, cooldown_hours):
    """
    Evita spam. Si la misma señal se mandó hace menos de cooldown_hours, no se repite.
    """
    last = state.get("last_alerts", {}).get(key)
    if not last:
        return True

    try:
        last_dt = datetime.fromisoformat(last)
        return utc_now() - last_dt >= timedelta(hours=cooldown_hours)
    except Exception:
        return True


def mark_alert_sent(state, key):
    state.setdefault("last_alerts", {})[key] = utc_now().isoformat()


def send_telegram(message: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram secrets missing. Message would be:")
        print(message)
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    r = requests.post(url, json=payload, timeout=HTTP_TIMEOUT)
    r.raise_for_status()


def format_money_eur(value):
    if value is None:
        return "N/A"
    return f"{value:,.0f} €"


def format_musd(value):
    if value is None:
        return "N/A"
    return f"{value:+.1f} M$"


def calculate_rsi(series: pd.Series, period=14):
    if series is None or len(series) < period + 2:
        return None

    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    # Wilder-style smoothing
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, pd.NA)
    rsi = 100 - (100 / (1 + rs))

    latest = rsi.iloc[-1]
    if pd.isna(latest):
        return None
    return float(latest)


def sma(series: pd.Series, period: int):
    if series is None or len(series) < period:
        return None
    value = series.rolling(period).mean().iloc[-1]
    return None if pd.isna(value) else float(value)


def pct_change(current, previous):
    if current is None or previous in [None, 0]:
        return None
    return (current / previous - 1) * 100


def drawdown_from_high(series: pd.Series, lookback: int):
    if series is None or len(series) < lookback:
        return None
    window = series.tail(lookback)
    high = float(window.max())
    last = float(window.iloc[-1])
    if high == 0:
        return None
    return (last / high - 1) * 100


# =============================================================================
# BTC DATA
# =============================================================================

def get_btc_price_eur():
    """
    Fallback chain:
    1) CoinGecko
    2) Coinbase
    3) Kraken
    """
    errors = []

    # 1) CoinGecko
    try:
        data = request_json(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": "bitcoin", "vs_currencies": "eur"},
        )
        return float(data["bitcoin"]["eur"]), "coingecko"
    except Exception as e:
        errors.append(f"CoinGecko price error: {e}")

    # 2) Coinbase
    try:
        data = request_json("https://api.coinbase.com/v2/prices/BTC-EUR/spot")
        return float(data["data"]["amount"]), "coinbase"
    except Exception as e:
        errors.append(f"Coinbase price error: {e}")

    # 3) Kraken
    try:
        data = request_json(
            "https://api.kraken.com/0/public/Ticker",
            params={"pair": "XBTEUR"},
        )
        result = next(iter(data["result"].values()))
        return float(result["c"][0]), "kraken"
    except Exception as e:
        errors.append(f"Kraken price error: {e}")

    raise RuntimeError("Could not fetch BTC/EUR price. " + " | ".join(errors))


def get_btc_daily_prices(days=365):
    """
    CoinGecko market_chart histórico.
    """
    data = request_json(
        "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart",
        params={"vs_currency": "eur", "days": days, "interval": "daily"},
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
    """
    Alternative.me Fear & Greed Index.
    """
    try:
        data = request_json("https://api.alternative.me/fng/", params={"limit": 1})
        item = data["data"][0]
        return {
            "value": int(item["value"]),
            "classification": item.get("value_classification", "N/A"),
            "timestamp": item.get("timestamp"),
        }
    except Exception as e:
        print(f"Fear & Greed error: {e}")
        return {"value": None, "classification": "N/A", "error": str(e)}


def get_binance_btc_funding(limit=8):
    """
    Funding BTCUSDT perpetual. Es proxy de estrés/posicionamiento.
    """
    try:
        data = request_json(
            "https://fapi.binance.com/fapi/v1/fundingRate",
            params={"symbol": "BTCUSDT", "limit": limit},
        )
        rates = [float(x["fundingRate"]) for x in data]
        latest = rates[-1] if rates else None
        negative_count = sum(1 for r in rates[-5:] if r < 0)
        avg_5 = sum(rates[-5:]) / min(len(rates), 5) if rates else None
        return {
            "latest": latest,
            "avg_5": avg_5,
            "negative_count_5": negative_count,
        }
    except Exception as e:
        print(f"Binance funding error: {e}")
        return {"latest": None, "avg_5": None, "negative_count_5": None, "error": str(e)}


def get_coinmetrics_mvrv():
    """
    MVRV aproximado por CoinMetrics Community API.
    Nota: no es MVRV Z-Score; es MVRV current ratio si la métrica está disponible.
    """
    candidates = ["CapMVRVCur", "CapMVRVFreeFloat"]
    for metric in candidates:
        try:
            data = request_json(
                "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics",
                params={
                    "assets": "btc",
                    "metrics": metric,
                    "frequency": "1d",
                    "page_size": 10,
                    "pretty": "false",
                },
            )
            rows = data.get("data", [])
            rows = [r for r in rows if r.get(metric) is not None]
            if not rows:
                continue
            latest = rows[-1]
            return {
                "metric": metric,
                "value": float(latest[metric]),
                "time": latest.get("time"),
            }
        except Exception as e:
            print(f"CoinMetrics {metric} error: {e}")

    return {"metric": None, "value": None, "time": None}


def get_latest_etf_flows():
    """
    ETF flows.
    Prioridad:
    1) Variables/Secrets manuales: ETF_DATE, ETF_TOTAL_MUSD, ETF_IBIT_MUSD
    2) Farside scraper: útil en local o self-hosted runner. En GitHub hosted suele devolver 403.
    3) N/A sin romper el bot
    """
    manual_total = safe_float(ETF_TOTAL_MUSD_ENV)
    manual_ibit = safe_float(ETF_IBIT_MUSD_ENV)

    if ETF_DATE_ENV and (manual_total is not None or manual_ibit is not None):
        return {
            "date": ETF_DATE_ENV,
            "ibit": manual_ibit,
            "total": manual_total,
            "source": "manual_env",
            "available": True,
        }

    urls = [
        "https://farside.co.uk/btc/",
        "https://farside.co.uk/bitcoin-etf-flow-all-data/",
    ]

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

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
            soup = BeautifulSoup(r.text, "html.parser")
            text = soup.get_text(" ")
            text = text.replace("\xa0", " ")
            text = re.sub(r"\s+", " ", text)

            matches = list(date_regex.finditer(text))
            rows = []

            for idx, match in enumerate(matches):
                date = match.group(0)
                start = match.end()
                end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
                block = text[start:end]

                for stopper in ["Average", "Maximum", "Minimum", "Source:", "All data"]:
                    if stopper in block:
                        block = block.split(stopper)[0]

                nums = number_regex.findall(block)

                # Farside BTC order commonly:
                # Total, IBIT, FBTC, BITB, ARKB, BTCO, EZBC, BRRR, HODL, BTCW, MSBT, GBTC, BTC
                if len(nums) >= 13:
                    values = nums[:13]
                    rows.append(
                        {
                            "date": date,
                            "total": parse_number(values[0]),
                            "ibit": parse_number(values[1]),
                        }
                    )

            if rows:
                latest = rows[-1]
                latest["source"] = "farside_scrape"
                latest["available"] = True
                return latest

        except Exception as e:
            last_error = str(e)
            print(f"Farside error with {url}: {e}")

    return {
        "date": "N/A",
        "ibit": None,
        "total": None,
        "source": "unavailable",
        "available": False,
        "reason": last_error or "ETF flows unavailable",
    }


# =============================================================================
# FREE STOCK/ETF SCANNER — STOOQ
# =============================================================================

def stooq_symbol(symbol: str):
    """
    Stooq suele usar .us para acciones/ETFs USA.
    En config puedes escribir directamente spy.us o qqq.us si quieres.
    """
    s = symbol.strip().lower()
    if "." in s:
        return s
    return f"{s}.us"


def get_stooq_history(symbol: str):
    url = "https://stooq.com/q/d/l/"
    params = {"s": stooq_symbol(symbol), "i": "d"}
    try:
        r = requests.get(url, params=params, timeout=HTTP_TIMEOUT)
        r.raise_for_status()
        text = r.text.strip()
        if "No data" in text or len(text) < 50:
            raise RuntimeError("No Stooq data")

        from io import StringIO
        df = pd.read_csv(StringIO(text))
        df.columns = [c.lower() for c in df.columns]
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        df = df.dropna(subset=["date", "close"])
        return df.sort_values("date").reset_index(drop=True)
    except Exception as e:
        print(f"Stooq error for {symbol}: {e}")
        return None


def scan_stocks(config):
    stock_cfg = config.get("stocks", {})
    if not stock_cfg.get("enabled", False):
        return []

    watchlist = stock_cfg.get("watchlist", [])
    max_items = int(stock_cfg.get("max_items_per_run", 10))
    thresholds = stock_cfg.get("thresholds", {})

    min_drawdown = float(thresholds.get("min_drawdown_pct", -10))
    max_rsi = float(thresholds.get("max_rsi_daily", 35))
    reclaim_sma20 = bool(thresholds.get("require_close_above_sma20", False))

    opportunities = []

    for symbol in watchlist[:max_items]:
        df = get_stooq_history(symbol)
        if df is None or len(df) < 220:
            continue

        close = df["close"]
        last = float(close.iloc[-1])
        rsi = calculate_rsi(close)
        sma20 = sma(close, 20)
        sma50 = sma(close, 50)
        sma200 = sma(close, 200)
        dd_252 = drawdown_from_high(close, 252)

        score = 0
        reasons = []

        if dd_252 is not None and dd_252 <= min_drawdown:
            score += 25
            reasons.append(f"Drawdown 52s {dd_252:.1f}%")

        if rsi is not None and rsi <= max_rsi:
            score += 25
            reasons.append(f"RSI diario {rsi:.1f}")

        if sma200 is not None and last >= sma200:
            score += 10
            reasons.append("Precio sobre SMA200")

        if sma20 is not None and last >= sma20:
            score += 15
            reasons.append("Recupera SMA20")

        if reclaim_sma20 and sma20 is not None and last < sma20:
            score -= 20
            reasons.append("Aún no recupera SMA20")

        if score >= int(thresholds.get("alert_score", 50)):
            opportunities.append(
                {
                    "symbol": symbol,
                    "price": last,
                    "score": score,
                    "rsi": rsi,
                    "drawdown": dd_252,
                    "sma20": sma20,
                    "sma50": sma50,
                    "sma200": sma200,
                    "reasons": reasons,
                }
            )

        time.sleep(0.2)

    opportunities.sort(key=lambda x: x["score"], reverse=True)
    return opportunities


# =============================================================================
# BTC SIGNAL ENGINE
# =============================================================================

def btc_signal(config, state, force_send=False):
    btc_cfg = config["btc"]
    thresholds = btc_cfg["thresholds"]
    alert_cfg = config.get("alerts", {})
    cooldown_hours = int(alert_cfg.get("cooldown_hours", 6))
    alert_threshold = int(alert_cfg.get("btc_alert_score", 70))

    price, price_source = get_btc_price_eur()
    prices_df = get_btc_daily_prices(days=int(btc_cfg.get("history_days", 365)))
    close = prices_df["price"]

    rsi_daily = calculate_rsi(close)
    sma20 = sma(close, 20)
    sma50 = sma(close, 50)
    sma200 = sma(close, 200)
    dd30 = drawdown_from_high(close, 30)
    dd90 = drawdown_from_high(close, 90)

    etf = get_latest_etf_flows()
    fear = get_fear_and_greed()
    funding = get_binance_btc_funding()
    mvrv = get_coinmetrics_mvrv() if btc_cfg.get("enable_mvrv", True) else {"value": None}

    score = 0
    reasons = []
    actions = []
    blocks = []

    # Precio vs niveles
    triggered_levels = []
    for level in btc_cfg.get("levels", []):
        if price <= float(level["price_eur"]):
            triggered_levels.append(level)

    if triggered_levels:
        deepest = triggered_levels[-1]
        # Score por zona; no suma 15 por cada nivel para no inflar demasiado.
        score += min(35, 15 + 5 * len(triggered_levels))
        reasons.append(
            f"BTC en zona de órdenes: <= {deepest['price_eur']:,.0f} € ({deepest['name']})"
        )
        for level in triggered_levels:
            actions.append(
                f"Revisar orden límite: {level['amount_eur']:,.0f} € en {level['price_eur']:,.0f} €"
            )

    # RSI
    if rsi_daily is not None:
        if rsi_daily <= float(thresholds["rsi_daily_deep_buy"]):
            score += 25
            reasons.append(f"RSI diario capitulación: {rsi_daily:.1f}")
        elif rsi_daily <= float(thresholds["rsi_daily_buy"]):
            score += 15
            reasons.append(f"RSI diario sobrevendido: {rsi_daily:.1f}")

    # Momentum/reclaim solo si hay reclaim real
    rebound = btc_cfg["rebound"]
    if price >= float(rebound["reclaim_price_eur"]):
        score += 15
        reasons.append(f"Precio recupera reclaim: {rebound['reclaim_price_eur']:,.0f} €")
        actions.append("Preparar Fase B / Lump Sum reactivo; exigir confirmación adicional.")

        if rsi_daily is not None and rsi_daily >= float(thresholds["rsi_daily_confirm"]):
            score += 10
            reasons.append(f"RSI confirma momentum tras reclaim: {rsi_daily:.1f}")

    # SMA context
    if sma200 is not None:
        if price < sma200:
            score += 5
            reasons.append(f"Precio bajo SMA200: posible descuento / riesgo alto ({sma200:,.0f} €)")
        elif price > sma200 and price >= float(rebound["reclaim_price_eur"]):
            score += 5
            reasons.append("Precio sobre SMA200 y reclaim: estructura mejora")

    # Drawdown / capitulación
    if dd30 is not None and dd30 <= float(thresholds.get("drawdown_30d_buy_pct", -15)):
        score += 10
        reasons.append(f"Drawdown 30D relevante: {dd30:.1f}%")
    if dd90 is not None and dd90 <= float(thresholds.get("drawdown_90d_buy_pct", -25)):
        score += 10
        reasons.append(f"Drawdown 90D fuerte: {dd90:.1f}%")

    # ETF flows
    etf_total = etf.get("total")
    ibit = etf.get("ibit")

    if etf_total is not None:
        if etf_total >= float(thresholds["etf_total_strong_musd"]):
            score += 25
            reasons.append(f"ETF total fuerte: {format_musd(etf_total)}")
        elif etf_total >= float(thresholds["etf_total_green_musd"]):
            score += 15
            reasons.append(f"ETF total positivo: {format_musd(etf_total)}")
        elif etf_total <= float(thresholds["etf_block_musd"]):
            score -= 25
            blocks.append(f"ETF total bloquea compras tácticas: {format_musd(etf_total)}")

    if ibit is not None:
        if ibit >= float(thresholds["ibit_strong_musd"]):
            score += 20
            reasons.append(f"IBIT fuerte: {format_musd(ibit)}")
        elif ibit >= float(thresholds["ibit_green_musd"]):
            score += 12
            reasons.append(f"IBIT positivo relevante: {format_musd(ibit)}")
        elif ibit <= float(thresholds["ibit_block_musd"]):
            score -= 20
            blocks.append(f"IBIT bloquea compras tácticas: {format_musd(ibit)}")

    # Fear & Greed
    fg = fear.get("value")
    if fg is not None:
        if fg <= int(thresholds.get("fear_extreme", 25)):
            score += 15
            reasons.append(f"Fear & Greed extremo: {fg} ({fear.get('classification')})")
        elif fg <= int(thresholds.get("fear_buy", 40)):
            score += 8
            reasons.append(f"Fear & Greed en miedo: {fg} ({fear.get('classification')})")
        elif fg >= int(thresholds.get("greed_block", 75)):
            score -= 10
            blocks.append(f"Sentimiento codicioso: {fg} ({fear.get('classification')})")

    # Funding
    neg_count = funding.get("negative_count_5")
    avg_funding_5 = funding.get("avg_5")
    if neg_count is not None:
        if neg_count >= int(thresholds.get("funding_negative_count_buy", 3)):
            score += 8
            reasons.append(f"Funding negativo {neg_count}/5 últimas ventanas")
        elif avg_funding_5 is not None and avg_funding_5 > float(thresholds.get("funding_overheated", 0.0002)):
            score -= 8
            blocks.append(f"Funding elevado/promercado: media 5 = {avg_funding_5:.5f}")

    # MVRV current ratio
    mvrv_value = mvrv.get("value")
    if mvrv_value is not None:
        if mvrv_value <= float(thresholds.get("mvrv_current_deep_buy", 1.05)):
            score += 18
            reasons.append(f"MVRV current muy bajo: {mvrv_value:.2f}")
        elif mvrv_value <= float(thresholds.get("mvrv_current_buy", 1.35)):
            score += 10
            reasons.append(f"MVRV current atractivo: {mvrv_value:.2f}")
        elif mvrv_value >= float(thresholds.get("mvrv_current_hot", 2.8)):
            score -= 10
            blocks.append(f"MVRV current alto: {mvrv_value:.2f}")

    # Clamp
    score = max(0, min(100, int(round(score))))

    # Status
    if score >= 85:
        status = "🟢 BTC STRONG BUY"
    elif score >= 70:
        status = "🟠 BTC PARTIAL BUY"
    elif score >= 55:
        status = "🟡 BTC WATCH"
    else:
        status = "⚪ SIN SEÑAL"

    # Alert key based on regime, not exact price, to reduce spam.
    signal_bucket = "none"
    if triggered_levels:
        signal_bucket = f"limit_{triggered_levels[-1]['price_eur']}"
    elif price >= float(rebound["reclaim_price_eur"]):
        signal_bucket = "reclaim"
    elif score >= 70:
        signal_bucket = "score70"
    alert_key = f"btc::{signal_bucket}::{status}"

    reasons_text = "\n".join("- " + html.escape(r) for r in reasons) if reasons else "- Ninguna señal relevante"
    actions_text = "\n".join("- " + html.escape(a) for a in actions) if actions else "- No comprar; seguir esperando"
    blocks_text = "\n".join("- " + html.escape(b) for b in blocks) if blocks else "- Ninguno"

    rsi_text = f"{rsi_daily:.1f}" if rsi_daily is not None else "N/A"
    sma20_text = format_money_eur(sma20)
    sma50_text = format_money_eur(sma50)
    sma200_text = format_money_eur(sma200)
    dd30_text = f"{dd30:.1f}%" if dd30 is not None else "N/A"
    dd90_text = f"{dd90:.1f}%" if dd90 is not None else "N/A"
    fg_text = f"{fg} / {fear.get('classification')}" if fg is not None else "N/A"
    funding_text = (
        f"latest={funding.get('latest'):.5f}, avg5={funding.get('avg_5'):.5f}, neg5={funding.get('negative_count_5')}"
        if funding.get("latest") is not None and funding.get("avg_5") is not None
        else "N/A"
    )
    mvrv_text = (
        f"{mvrv_value:.2f} ({mvrv.get('metric')})"
        if mvrv_value is not None
        else "N/A"
    )

    message = f"""
<b>{html.escape(status)}</b>

<b>Score:</b> {score}/100
<b>Precio BTC/EUR:</b> {price:,.0f} €
<b>Fuente precio:</b> {html.escape(price_source)}

<b>Técnico:</b>
RSI diario: {rsi_text}
SMA20: {sma20_text}
SMA50: {sma50_text}
SMA200: {sma200_text}
Drawdown 30D: {dd30_text}
Drawdown 90D: {dd90_text}

<b>ETF flows:</b>
Fecha: {html.escape(str(etf.get("date")))}
Fuente: {html.escape(str(etf.get("source")))}
IBIT: {format_musd(ibit)}
Total: {format_musd(etf_total)}

<b>Sentimiento / Derivados / On-chain:</b>
Fear & Greed: {html.escape(fg_text)}
Funding BTCUSDT: {html.escape(funding_text)}
MVRV current: {html.escape(mvrv_text)}

<b>Razones:</b>
{reasons_text}

<b>Bloqueos/Riesgos:</b>
{blocks_text}

<b>Acciones sugeridas:</b>
{actions_text}

<b>Hora:</b> {utc_now().strftime("%Y-%m-%d %H:%M UTC")}
""".strip()

    print(message)

    send = force_send or score >= alert_threshold
    if send:
        if force_send or should_send_alert(state, alert_key, cooldown_hours):
            send_telegram(message)
            mark_alert_sent(state, alert_key)
        else:
            print(f"Alert suppressed by cooldown: {alert_key}")


def stock_signal(config, state, force_send=False):
    opportunities = scan_stocks(config)
    if not opportunities:
        print("No stock/ETF opportunities.")
        return

    alert_cfg = config.get("alerts", {})
    cooldown_hours = int(alert_cfg.get("cooldown_hours", 6))
    key = "stocks::opportunities"

    lines = []
    for item in opportunities[:8]:
        rsi = f"{item['rsi']:.1f}" if item["rsi"] is not None else "N/A"
        dd = f"{item['drawdown']:.1f}%" if item["drawdown"] is not None else "N/A"
        reasons = ", ".join(item["reasons"])
        lines.append(
            f"• <b>{html.escape(item['symbol'])}</b> — score {item['score']}, "
            f"precio {item['price']:.2f}, RSI {rsi}, DD52s {dd}\n"
            f"  {html.escape(reasons)}"
        )

    message = f"""
<b>📈 STOCK / ETF WATCHLIST</b>

{chr(10).join(lines)}

<b>Hora:</b> {utc_now().strftime("%Y-%m-%d %H:%M UTC")}
""".strip()

    print(message)

    if force_send or should_send_alert(state, key, cooldown_hours):
        send_telegram(message)
        mark_alert_sent(state, key)
    else:
        print("Stock alert suppressed by cooldown.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Send Telegram even if there is no signal/cooldown")
    parser.add_argument("--btc-only", action="store_true", help="Run only BTC module")
    parser.add_argument("--stocks-only", action="store_true", help="Run only stocks module")
    args = parser.parse_args()

    config = load_config()
    state = load_state()

    try:
        if not args.stocks_only and config.get("btc", {}).get("enabled", False):
            btc_signal(config, state, force_send=args.force)

        if not args.btc_only and config.get("stocks", {}).get("enabled", False):
            stock_signal(config, state, force_send=args.force)

    finally:
        save_state(state)


if __name__ == "__main__":
    main()
