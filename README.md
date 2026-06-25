# Portfolio Tracker

You build a portfolio PDF in Claude.ai — that's the single source of truth
for what you hold and how many shares. Each run (weekly), the system:

1. reads your holdings from that PDF,
2. fetches current prices and builds an **updated-values PDF** (email attachment),
3. researches every position with Claude + web search and writes it as the
   **email body** — single-name research for conviction holdings, a shared
   **macro** briefing for your index funds.

The system does NOT build your portfolio. You do that in Claude.ai, where
you can iterate. This system refreshes values and researches what you hold.

---

## How it works

    state/current/portfolio.pdf      ← source of truth (holdings + shares)
            │
            ▼  make digest  (weekly)
      extract holdings ─► fetch prices ─► updated-values PDF ──► attachment
                       └► research:  macro for index funds      ──► email body
                                     single-name for conviction
            │
            ▼
    email: body = research, attachment = updated-values PDF
    state/outputs/history/<ts>_run/{portfolio_updated.pdf, research.md, ...}

No server, nothing to restart. Updating the portfolio = drop a new PDF +
`make accept-pdf`. The file on disk is the state.

---

## Layers

    config.py        tunables: model, paths, schedule, ticker→symbol map,
                     and INDEX_TICKERS (which tickers are broad index funds).
                     Anything that varies with the PORTFOLIO is NOT here —
                     it comes from the PDF.

    core/            domain logic
      holdings.py    Position model + extract holdings (and thesis notes) from PDF
      prices.py      current prices (yfinance, swappable; portfolio-driven)
      research.py    macro vs single-name research, driven by the holdings
      digest.py      build the valuations markdown + the research markdown
      claude_client  thin Anthropic API wrapper

    io_layer/        plumbing
      intake.py      accept a PDF → state/current/
      storage.py     write each run's artifacts to history/
      render.py      markdown → PDF
      send.py        deliver: research body + PDF attachment (STUBBED)

    sandbox/         iterate on one piece (try_research, try_prices, try_extract)
    tests/           offline unit tests + online smoke test

core never imports io_layer. The boundary stays clean.

---

## Setup

    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    brew install pango          # WeasyPrint native dep (macOS)

    mkdir -p .secrets
    echo "ANTHROPIC_API_KEY=sk-ant-..." > .secrets/.env

Verify:

    make test          # offline plumbing — 40/40, no key needed
    make test-online   # confirms your API key works

---

## Daily use

    1. Build a portfolio PDF in Claude.ai. Download it.
    2. Drop it into portfolio_inbox/.
    3. make accept-pdf      # becomes state/current/portfolio.pdf
    4. make digest          # updated-values PDF + research, then (stub) send

Output lands in state/outputs/history/<timestamp>_run/. Delivery is stubbed
— it prints what would be emailed. See "Enabling email".

### Iterate on research (the part that matters)

    make research T=OKLO                    # one conviction ticker
    make research-macro T="VUAA WEXE IS3N"  # the macro briefing
    make prices                             # price the current portfolio
    make extract                            # see how the PDF reads back

Tune the prompts in core/research.py until the output is worth reading.

---

## Index vs conviction

config.INDEX_TICKERS lists your broad index/market funds. Those get ONE
shared macro briefing (market backdrop) instead of single-name research.
Everything else is treated as a conviction position and researched
individually, using any thesis note found in the PDF. Edit INDEX_TICKERS
as your index spine changes.

---

## Prices: confirm symbols once

European ETFs need exchange suffixes for yfinance (.L, .DE, ...). US names
work bare. config.PRICE_SYMBOLS only holds the non-US exceptions, and those
suffixes are GUESSES. Run `make prices` and fix any FAIL by editing
config.PRICE_SYMBOLS.

---

## Enabling email

Delivery is behind a one-line swap in io_layer/send.py. Implement a
GmailSender (lift auth/ + Gmail-send from legacy/), then set:

    ACTIVE_SENDER = GmailSender()

The pipeline calls send(subject, body_markdown, attachment_path) and
doesn't care which backend is behind it.

---

## Stubbed / not done

- Email delivery (stubbed to print; swap in send.py).
- Scheduling (run `make digest` manually; cron later).
- FX conversion (totals grouped by native currency, not converted).
- snapshot.json per run (easy add later if you want a value time-series).
