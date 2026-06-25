"""Iterate on research output for a single ticker.

Usage:
    python -m sandbox.try_research OKLO                 # DEEP briefing (default)
    python -m sandbox.try_research OKLO --brief         # one-line brief
    python -m sandbox.try_research ASTS "launch binary" # deep, with a thesis
    python -m sandbox.try_research --macro VUAA WEXE     # macro (deep)
    python -m sandbox.try_research --macro VUAA --brief  # macro (brief)

Single-name deep research lives here on purpose — this is the "shelved"
deep mode you invoke when you want the full treatment on one position.
"""

import sys

from core.research import (
    research_position_deep, research_brief, research_macro,
)


def main():
    args = sys.argv[1:]
    if not args:
        print("usage: python -m sandbox.try_research TICKER [thesis] [--brief]")
        print("   or: python -m sandbox.try_research --macro TICK1 TICK2 ... [--brief]")
        sys.exit(1)

    brief = "--brief" in args
    args = [a for a in args if a != "--brief"]

    if args and args[0] == "--macro":
        index_tickers = args[1:] or ["broad market ETFs"]
        print(f"Macro research ({'brief' if brief else 'deep'}) for "
              f"{', '.join(index_tickers)}...\n")
        entry = research_macro(index_tickers, brief=brief)
    else:
        ticker = args[0].upper()
        thesis = args[1] if len(args) > 1 else ""
        print(f"Researching {ticker} ({'brief' if brief else 'deep'})...\n")
        entry = research_brief(ticker, thesis) if brief \
            else research_position_deep(ticker, thesis)

    if not entry.ok:
        print(f"FAILED: {entry.note}")
        sys.exit(1)
    print(entry.as_markdown())


if __name__ == "__main__":
    main()
