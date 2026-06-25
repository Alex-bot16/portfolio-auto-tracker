"""FX — convert values into one display currency for a single grand total.

We keep the native per-currency breakdown (clarity), AND add a converted
grand total so "what am I worth" has one number. Rates come from yfinance
FX pairs (e.g. "USDCHF=X"); a same-currency conversion is rate 1.0.

Like prices, the backend is isolated in _rate(); swap it to change source.
Failures are soft — an unobtainable rate means that currency's lines are
excluded from the converted total and flagged, never crash the run.
"""

from dataclasses import dataclass

import config


@dataclass
class Rate:
    pair: str
    rate: float
    ok: bool
    note: str = ""


_cache: dict = {}   # (from,to) -> Rate, within a single process run


def to_display(value: float, from_ccy: str, display_ccy: str) -> tuple[float, bool]:
    """Convert value from from_ccy into display_ccy.

    Returns (converted_value, ok). If the rate can't be obtained, returns
    (0.0, False) so the caller can exclude+flag rather than show garbage.
    """
    if not from_ccy:
        return 0.0, False
    if from_ccy == display_ccy:
        return value, True
    r = _get_rate(from_ccy, display_ccy)
    if not r.ok:
        return 0.0, False
    return value * r.rate, True


def _get_rate(from_ccy: str, to_ccy: str) -> Rate:
    key = (from_ccy, to_ccy)
    if key in _cache:
        return _cache[key]
    r = _fetch_rate(from_ccy, to_ccy)
    _cache[key] = r
    return r


def _fetch_rate(from_ccy: str, to_ccy: str) -> Rate:
    """Fetch one FX rate via yfinance. Swap this body to change source."""
    pair = f"{from_ccy}{to_ccy}=X"
    try:
        import yfinance as yf
    except ImportError:
        return Rate(pair, 0.0, False, "yfinance not installed")
    try:
        t = yf.Ticker(pair)
        last = t.fast_info.last_price
        if last is None or float(last) <= 0:
            return Rate(pair, 0.0, False, "no rate")
        return Rate(pair, float(last), True)
    except Exception as e:
        return Rate(pair, 0.0, False, f"{type(e).__name__}: {e}")
