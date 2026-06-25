"""Prices — fetch current market prices for the profile's tickers.

Driven by the profile (the machine source of truth), not a config list.
The price symbol comes from each position's symbol_override (set when the
profile was generated, editable in profile.json); otherwise the bare
ticker. Unpriceable holdings fall back downstream to their PDF value, so
a failed fetch never crashes a run or leaks an error into the document.

Optional on-disk cache (state/price_cache.json) with a TTL avoids
re-hitting the price source on repeated runs while testing. A real weekly
run finds the cache stale and fetches fresh.

yfinance backend isolated in _fetch_one(); swap to change provider.
"""

import json
import time
from dataclasses import dataclass
from pathlib import Path

import config


@dataclass
class Quote:
    ticker: str
    symbol: str
    price: float
    currency: str
    ok: bool
    note: str = ""


def fetch_quotes(ticker_to_symbol: dict, use_cache: bool = True,
                 ttl_seconds: int = 3600) -> dict:
    """Fetch prices for {ticker: symbol}. Returns {ticker: Quote}.

    use_cache reads/writes state/price_cache.json; entries fresher than
    ttl_seconds are reused. Failures are soft (ok=False + note).
    """
    cache = _load_cache() if use_cache else {}
    now = time.time()
    quotes = {}

    for ticker, symbol in ticker_to_symbol.items():
        hit = cache.get(symbol)
        if use_cache and hit and (now - hit.get("ts", 0)) < ttl_seconds:
            quotes[ticker] = Quote(ticker, symbol, hit["price"],
                                   hit["currency"], True, "cache")
            continue
        q = _fetch_one(ticker, symbol)
        quotes[ticker] = q
        if q.ok:
            cache[symbol] = {"price": q.price, "currency": q.currency, "ts": now}

    if use_cache:
        _save_cache(cache)
    return quotes


def _fetch_one(ticker: str, symbol: str) -> Quote:
    try:
        import yfinance as yf
    except ImportError:
        return Quote(ticker, symbol, 0.0, "", False, "yfinance not installed")
    try:
        t = yf.Ticker(symbol)
        info = t.fast_info
        last = info.last_price
        if last is None:
            return Quote(ticker, symbol, 0.0, "", False,
                         "no price (symbol may be wrong/delisted)")
        price = float(last)
        currency = getattr(info, "currency", "") or ""
        if price <= 0:
            return Quote(ticker, symbol, 0.0, currency, False, "price came back zero")
        return Quote(ticker, symbol, price, currency, True)
    except Exception as e:
        return Quote(ticker, symbol, 0.0, "", False, f"{type(e).__name__}: {e}")


def _load_cache() -> dict:
    try:
        return json.loads(Path(config.PRICE_CACHE_PATH).read_text())
    except Exception:
        return {}


def _save_cache(cache: dict) -> None:
    try:
        Path(config.PRICE_CACHE_PATH).parent.mkdir(parents=True, exist_ok=True)
        Path(config.PRICE_CACHE_PATH).write_text(json.dumps(cache, indent=2))
    except Exception:
        pass  # cache is best-effort; never fail a run over it
