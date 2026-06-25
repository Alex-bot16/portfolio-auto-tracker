"""Price every ticker in the saved profile (profile-driven).

Usage:  python -m sandbox.try_prices

Reads state/profile.json, prices each holding using its symbol_override
(or bare ticker). FAILs that have a PDF value still fall back to it in a
real run — but fixing the symbol_override in profile.json gives a live
price instead.
"""

import config
from core import profile as profile_mod
from core.prices import fetch_quotes


def main():
    try:
        prof = profile_mod.load()
    except FileNotFoundError:
        print(f"No profile at {config.PROFILE_PATH}.")
        print("Run `make accept-pdf` first to generate it from a PDF.")
        return

    ticker_symbol = {p.ticker: prof.symbol_for(p.ticker) for p in prof.positions}
    print(f"{len(ticker_symbol)} tickers in profile\n")

    # bypass cache here so you always see a live result while iterating
    quotes = fetch_quotes(ticker_symbol, use_cache=False)
    ok, bad = [], []
    for ticker, symbol in ticker_symbol.items():
        q = quotes[ticker]
        if q.ok:
            print(f"  OK    {ticker:8s} ({symbol:12s}) {q.price:>12,.2f} {q.currency}")
            ok.append(ticker)
        else:
            print(f"  FAIL  {ticker:8s} ({symbol:12s}) {q.note}")
            bad.append(ticker)

    print(f"\n{len(ok)} ok, {len(bad)} failed")
    if bad:
        print("\nThese fall back to PDF value in a real run. To price them")
        print("live, set a correct symbol_override in profile.json:")
        for t in bad:
            print(f'    "{t}": try the right exchange suffix '
                  f'(current: "{prof.symbol_for(t)}")')


if __name__ == "__main__":
    main()
