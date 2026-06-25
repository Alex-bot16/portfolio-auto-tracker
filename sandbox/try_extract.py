"""Extract the current PDF into a profile and print it (does NOT save).

Usage:  python -m sandbox.try_extract

Confirms the PDF reads back cleanly — tickers, shares, classification
(index/conviction/sandbox), thesis notes, symbol overrides, and any
cash/savings/bank wealth — before committing it via `make accept-pdf`.
"""

import config
from core.holdings import extract_to_profile


def main():
    if not config.CURRENT_PDF.exists():
        print(f"No portfolio at {config.CURRENT_PDF}.")
        print("Drop a PDF in portfolio_inbox/ and run `make accept-pdf` "
              "(or copy one to that path) first.")
        return

    print(f"Extracting from {config.CURRENT_PDF} (not saving)...\n")
    prof = extract_to_profile(config.CURRENT_PDF)

    print(f"display currency: {prof.display_currency}   "
          f"sandbox accounts: {prof.sandbox_accounts}\n")

    print(f"{len(prof.positions)} positions "
          f"({len(prof.conviction())} conviction, {len(prof.index())} index, "
          f"{len(prof.sandbox())} sandbox):\n")
    for p in prof.positions:
        val = (f"{p.pdf_value_native:,.2f} {p.currency}"
               if p.pdf_value_native is not None else "—")
        acct = f" [{p.account}]" if p.account else ""
        sym = f"  ->{p.symbol_override}" if p.symbol_override else ""
        print(f"  {p.ticker:8s} {p.shares:>12g}  {p.name}{acct}  "
              f"({val})  <{p.classification}>{sym}")
        if p.thesis:
            print(f"           thesis: {p.thesis}")

    print(f"\n{len(prof.wealth)} wealth lines:\n")
    for w in prof.wealth:
        acct = f" [{w.account}]" if w.account else ""
        print(f"  {w.label}{acct}: {w.value_native:,.2f} {w.currency}")

    print("\n(To commit this as the machine source of truth, run "
          "`make accept-pdf`.)")


if __name__ == "__main__":
    main()
