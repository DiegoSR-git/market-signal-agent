import os
import math
import yaml
import requests
import pandas as pd
import re
from bs4 import BeautifulSoup
from datetime import datetime, timezone

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

COINGECKO_PRICE_URL = "https://api.coingecko.com/api/v3/simple/price"
COINGECKO_HISTORY_URL = "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart"
FARSIDE_URL = "https://farside.co.uk/bitcoin-etf-flow-all-data/"


def load_config():
    with open("config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def send_telegram(message: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram secrets missing")
        print(message)
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    r = requests.post(url, json=payload, timeout=20)
    r.raise_for_status()


def get_btc_price_eur():
    params = {
        "ids": "bitcoin",
        "vs_currencies": "eur",
    }
    r = requests.get(COINGECKO_PRICE_URL, params=params, timeout=20)
    r.raise_for_status()
    return float(r.json()["bitcoin"]["eur"])


def get_btc_daily_prices(days=120):
    params = {
        "vs_currency": "eur",
        "days": days,
        "interval": "daily",
    }
    r = requests.get(COINGECKO_HISTORY_URL, params=params, timeout=20)
    r.raise_for_status()
    data = r.json()["prices"]

    df = pd.DataFrame(data, columns=["timestamp", "price"])
    df["date"] = pd.to_datetime(df["timestamp"], unit="ms")
    df = df.drop_duplicates(subset=["date"])
    return df[["date", "price"]]


def calculate_rsi(series: pd.Series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    latest = rsi.iloc[-1]
    if math.isnan(latest):
        return None
    return float(latest)


def parse_number(x):
    if pd.isna(x):
        return 0.0

    s = str(x).strip()

    if s in ["-", "", "nan", "None"]:
        return 0.0

    negative = s.startswith("(") and s.endswith(")")
    s = s.replace("(", "").replace(")", "")
    s = s.replace(",", "")
    s = s.replace("$", "")
    s = s.replace("M", "")
    s = s.strip()

    try:
        value = float(s)
        return -value if negative else value
    except ValueError:
        return 0.0


def get_latest_etf_flows():
    """
    Parser robusto para Farside.
    No depende de pd.read_html(), porque Farside no siempre expone la tabla
    como <table> HTML estándar en GitHub Actions.
    """

    url = "https://farside.co.uk/bitcoin-etf-flow-all-data/"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0 Safari/537.36"
        )
    }

    try:
        r = requests.get(url, headers=headers, timeout=30)
        r.raise_for_status()

        soup = BeautifulSoup(r.text, "html.parser")
        text = soup.get_text("\n")

        # Normalizar líneas
        lines = [
            line.replace("\xa0", " ").strip()
            for line in text.splitlines()
            if line.replace("\xa0", " ").strip()
        ]

        # Columnas esperadas en Farside All Data:
        # Date, IBIT, FBTC, BITB, ARKB, BTCO, EZBC, BRRR, HODL,
        # BTCW, MSBT, GBTC, BTC, Total
        value_count = 13

        date_pattern = re.compile(r"^\d{1,2} [A-Za-z]{3} \d{4}$")

        rows = []
        i = 0

        while i < len(lines):
            if date_pattern.match(lines[i]):
                date = lines[i]
                values = lines[i + 1 : i + 1 + value_count]

                if len(values) == value_count:
                    row = {
                        "date": date,
                        "ibit": parse_number(values[0]),
                        "fbtc": parse_number(values[1]),
                        "bitb": parse_number(values[2]),
                        "arkb": parse_number(values[3]),
                        "btco": parse_number(values[4]),
                        "ezbc": parse_number(values[5]),
                        "brrr": parse_number(values[6]),
                        "hodl": parse_number(values[7]),
                        "btcw": parse_number(values[8]),
                        "msbt": parse_number(values[9]),
                        "gbtc": parse_number(values[10]),
                        "btc": parse_number(values[11]),
                        "total": parse_number(values[12]),
                    }
                    rows.append(row)

                i += 1 + value_count
            else:
                i += 1

        if not rows:
            print("Farside parser: no daily rows found")
            return {
                "date": "N/A",
                "ibit": None,
                "total": None,
            }

        latest = rows[-1]

        return {
            "date": latest["date"],
            "ibit": latest["ibit"],
            "total": latest["total"],
        }

    except Exception as e:
        print(f"Farside parser error: {e}")
        return {
            "date": "N/A",
            "ibit": None,
            "total": None,
        }


def btc_signal(config):
    btc_cfg = config["btc"]
    thresholds = btc_cfg["thresholds"]

    price = get_btc_price_eur()
    prices_df = get_btc_daily_prices(days=120)
    rsi_daily = calculate_rsi(prices_df["price"])
    rsi_text = f"{rsi_daily:.1f}" if rsi_daily is not None else "N/A"

    try:
        etf = get_latest_etf_flows()
    except Exception as e:
        etf = {
            "date": "N/A",
            "ibit": None,
            "total": None,
            "error": str(e),
        }

    score = 0
    reasons = []
    actions = []

    # Precio vs niveles
    for level in btc_cfg["levels"]:
        if price <= level["price_eur"]:
            score += 15
            reasons.append(
                f"Precio <= {level['price_eur']:,.0f} € ({level['name']})"
            )
            actions.append(
                f"Revisar compra/orden: {level['amount_eur']:,.0f} € en {level['price_eur']:,.0f} €"
            )

    # RSI diario
    if rsi_daily is not None:
        if rsi_daily <= thresholds["rsi_daily_buy"]:
            score += 20
            reasons.append(f"RSI diario sobrevendido: {rsi_daily:.1f}")
        elif rsi_daily >= thresholds["rsi_daily_confirm"]:
            score += 10
            reasons.append(f"RSI diario confirma momentum: {rsi_daily:.1f}")

    # ETF flows
    etf_total = etf.get("total")
    ibit = etf.get("ibit")

    if etf_total is not None:
        if etf_total >= thresholds["etf_total_strong_musd"]:
            score += 25
            reasons.append(f"ETF total fuerte: +{etf_total:.1f} M$")
        elif etf_total >= thresholds["etf_total_green_musd"]:
            score += 15
            reasons.append(f"ETF total positivo: +{etf_total:.1f} M$")
        elif etf_total <= thresholds["etf_block_musd"]:
            score -= 25
            reasons.append(f"ETF total bloquea compras: {etf_total:.1f} M$")

    if ibit is not None:
        if ibit >= thresholds["ibit_strong_musd"]:
            score += 20
            reasons.append(f"IBIT fuerte: +{ibit:.1f} M$")
        elif ibit >= thresholds["ibit_green_musd"]:
            score += 12
            reasons.append(f"IBIT positivo relevante: +{ibit:.1f} M$")
        elif ibit <= thresholds["ibit_block_musd"]:
            score -= 20
            reasons.append(f"IBIT bloquea compras: {ibit:.1f} M$")

    # Reclaim / rebote
    rebound = btc_cfg["rebound"]
    if price >= rebound["reclaim_price_eur"]:
        score += 15
        reasons.append(f"Precio recupera zona de reclaim: {rebound['reclaim_price_eur']:,.0f} €")
        actions.append("Preparar Fase B / Lump Sum reactivo si ETF confirma.")

    # Clasificación
    
    if score >= 85:
        status = "🟢 BTC STRONG BUY"
    elif score >= 70:
        status = "🟠 BTC PARTIAL BUY"
    elif score >= 55:
        status = "🟡 BTC WATCH"
    else:
        status = "⚪ SIN SEÑAL"

    message = f"""
<b>{status}</b>

<b>Score:</b> {score}/100
<b>Precio BTC/EUR:</b> {price:,.0f} €
<b>RSI diario:</b> {rsi_text}

<b>ETF flows Farside:</b>
Fecha: {etf.get("date")}
IBIT: {ibit if ibit is not None else "N/A"} M$
Total: {etf_total if etf_total is not None else "N/A"} M$

<b>Razones:</b>
{chr(10).join("- " + r for r in reasons) if reasons else "- Ninguna señal relevante"}

<b>Acciones sugeridas:</b>
{chr(10).join("- " + a for a in actions) if actions else "- No comprar; seguir esperando"}

<b>Hora:</b> {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}
""".strip()

    # Para evitar ruido: solo enviar si score >= 55
    if score >= 55:
        send_telegram(message)
    else:
        print(message)
        
    send_telegram(message)
    print(message)

def main():
    config = load_config()

    if config["btc"].get("enabled", False):
        btc_signal(config)


if __name__ == "__main__":
    main()
