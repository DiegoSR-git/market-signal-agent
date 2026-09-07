from unittest.mock import Mock, patch

from alpha_intraday.providers.alpaca import AlpacaMarketDataProvider, RateLimitError


def response(status, payload):
    r = Mock()
    r.status_code = status
    r.json.return_value = payload
    r.raise_for_status.return_value = None
    return r


@patch.dict("os.environ", {"ALPACA_API_KEY": "k", "ALPACA_SECRET_KEY": "s"})
def test_alpaca_intraday_bars_parses_official_response():
    payload = {"bars": [{"t": "2026-07-08T13:30:00Z", "o": 100, "h": 101, "l": 99, "c": 100.5, "v": 12345}]}
    with patch("requests.get", return_value=response(200, payload)) as get:
        bars = AlpacaMarketDataProvider(feed="iex").intraday_bars("NVDA")
    assert bars[0].timestamp.tzinfo is not None
    assert bars[0].close == 100.5
    assert get.call_args.kwargs["params"]["feed"] == "iex"
    assert "/v2/stocks/NVDA/bars" in get.call_args.args[0]


@patch.dict("os.environ", {"ALPACA_API_KEY": "k", "ALPACA_SECRET_KEY": "s"})
def test_alpaca_bars_requests_recent_desc_and_returns_ascending_limit():
    payload = {
        "bars": [
            {"t": "2026-07-08T13:32:00Z", "o": 102, "h": 103, "l": 101, "c": 102.5, "v": 3},
            {"t": "2026-07-08T13:31:00Z", "o": 101, "h": 102, "l": 100, "c": 101.5, "v": 2},
            {"t": "2026-07-08T13:30:00Z", "o": 100, "h": 101, "l": 99, "c": 100.5, "v": 1},
        ]
    }
    with patch("requests.get", return_value=response(200, payload)) as get:
        bars = AlpacaMarketDataProvider(feed="iex").intraday_bars("NVDA", limit=2)
    params = get.call_args.kwargs["params"]
    assert params["sort"] == "desc"
    assert params["limit"] >= 390
    assert [bar.close for bar in bars] == [101.5, 102.5]


@patch.dict("os.environ", {"ALPACA_API_KEY": "k", "ALPACA_SECRET_KEY": "s"})
def test_alpaca_rate_limit_raises_after_retries():
    with patch("requests.get", return_value=response(429, {})), patch("time.sleep"):
        try:
            AlpacaMarketDataProvider(retries=0).intraday_bars("NVDA")
        except RateLimitError:
            return
    raise AssertionError("RateLimitError esperado")
