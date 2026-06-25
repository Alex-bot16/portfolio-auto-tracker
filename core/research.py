"""Research — driven by the profile's classification.

  conviction positions -> single-name research (brief by default, deep on demand)
  index positions       -> ONE shared macro briefing
  sandbox positions     -> SKIPPED

Brief mode hard-constrains output to one newsletter-style line; deep mode
gives the full multi-section briefing and is shelved for on-demand use via
`make research T=...`.

Between research calls we pace (config.RESEARCH_PACE_SECONDS) and the
underlying client retries on 429 — together these keep us under the
per-minute token ceiling instead of failing into "unavailable".

A progress callback lets the caller print per-ticker status as it goes.
"""

import time
from dataclasses import dataclass

import config
from core import claude_client
from core.profile import Profile, ProfilePosition


@dataclass
class ResearchEntry:
    label: str
    raw_markdown: str
    ok: bool = True
    note: str = ""
    brief: bool = False

    def as_markdown(self) -> str:
        if self.brief:
            if not self.ok:
                return f"- **{self.label}** — _unavailable: {self.note}_"
            return self.raw_markdown.strip()
        header = f"### {self.label}\n\n"
        if not self.ok:
            return header + f"_Research unavailable: {self.note}_\n"
        return header + self.raw_markdown.strip() + "\n"


# ─── Prompts ─────────────────────────────────────────────────────────

_BRIEF_PROMPT = """\
Output EXACTLY ONE markdown bullet line and NOTHING ELSE. No preamble, no \
reasoning, no explanation of your process, no notes, no caveats.

Research the single most material development in the last ~2 weeks for this \
EXACT holding:
  name: {name}
  ticker: {ticker}
  market symbol: {symbol}
(thesis context: {thesis})

Search using the ticker and name. Your source link MUST be about THIS \
security ({ticker} / {symbol}) or its issuer — not a different company, \
fund, or listing. If you cannot find a source for THIS security, output the \
"no material developments" line rather than cite something else.

Then output ONLY:

- **{ticker}** — <one sentence, max 30 words, with one concrete number> ([source](URL))

If there is no material recent news, output ONLY:
- **{ticker}** — no material developments in the period.

One line. No other text. Never invent numbers or links.
"""

_DEEP_PROMPT = """\
You are a research assistant for a long-term retail investor. Research \
recent developments from roughly the last two weeks, material to the \
thesis, for this EXACT holding:
  name: {name}
  ticker: {ticker}
  market symbol: {symbol}
(thesis: {thesis})

Search using the ticker and name. Every source MUST be about THIS security \
({ticker} / {symbol}) or its issuer — not a different company, fund, or \
listing. If you cannot find material news for THIS security, say so.

Sections:
**What changed** — 2-4 bullets, each with a specific number and, where it \
aids accuracy, a SHORT direct quote (under 15 words).
**Sentiment** — one line: net bullish/bearish/mixed, why briefly.
**Sources** — bulleted source links, each a 2-4 word label.

Prefer primary sources; quotes under 15 words; if no material news say so; \
never invent figures or links; clean markdown, no preamble.
"""

_MACRO_BRIEF_PROMPT = """\
Output 2-3 markdown bullet lines and NOTHING ELSE — no preamble, no headers.

Write a short market-backdrop note for an investor whose index exposure is \
these broad ETFs: {tickers}. Search the last ~2 weeks of macro/market news. \
Each bullet is one sentence with one concrete number and one source link, \
and it ENDS with the subset of the tickers above that it actually bears on, \
in bold square brackets:

- <one sentence with a number> ([source](URL)) **[TICKER, TICKER]**

Tag every bullet with at least one ticker, using ONLY tickers from this \
list: {tickers}. 2-3 bullets max. Never invent figures or links.
"""

_MACRO_DEEP_PROMPT = """\
Market-backdrop briefing for an investor whose index exposure is broad \
ETFs: {tickers}. Search the last ~2 weeks of macro/market news.

**Market backdrop** — 3-5 bullets, each with a specific number and, where \
useful, a SHORT quote (under 15 words). End each bullet with the subset of \
{tickers} it bears on, in bold square brackets, e.g. **[VUAA, IS3N]**.
**Sentiment** — one line: risk-on / risk-off / mixed, why briefly.
**Sources** — bulleted source links, each a 2-4 word label.

Prefer primary/major sources; quotes under 15 words; never invent figures \
or links; clean markdown, no preamble.
"""


# ─── Single-call entry points ────────────────────────────────────────

def research_brief(ticker: str, thesis: str = "",
                   name: str = "", symbol: str = "") -> ResearchEntry:
    prompt = _BRIEF_PROMPT.format(ticker=ticker, name=name or ticker,
                                  symbol=symbol or ticker,
                                  thesis=thesis or "long-term holding")
    return _run(ticker, prompt, brief=True)


def research_position_deep(ticker: str, thesis: str = "",
                           name: str = "", symbol: str = "") -> ResearchEntry:
    prompt = _DEEP_PROMPT.format(ticker=ticker, name=name or ticker,
                                 symbol=symbol or ticker,
                                 thesis=thesis or "long-term holding (no notes)")
    return _run(ticker, prompt, brief=False)


def research_macro(index_tickers: list, brief: bool = True) -> ResearchEntry:
    tickers_str = ", ".join(index_tickers) if index_tickers else "broad market ETFs"
    tmpl = _MACRO_BRIEF_PROMPT if brief else _MACRO_DEEP_PROMPT
    return _run("MARKET", tmpl.format(tickers=tickers_str), brief=brief)


# ─── Portfolio-level (profile-driven) ────────────────────────────────

def research_profile(profile: Profile, on_progress=None) -> list:
    """Research a profile for the digest.

    - index positions -> one macro block.
    - conviction positions -> single-name (brief per config).
    - sandbox positions -> skipped.
    on_progress(label, status) is called as each block starts/finishes,
    so the caller can print live progress.

    Paces between calls and relies on client retry to ride out rate limits.
    """
    brief = config.RESEARCH_BRIEF_FOR_EMAIL

    # Dedup conviction tickers (across accounts) preserving order.
    seen = set()
    conviction = []
    for p in profile.conviction():
        if p.ticker in seen:
            continue
        seen.add(p.ticker)
        conviction.append(p)

    if config.RESEARCH_LIMIT is not None:
        conviction = conviction[:config.RESEARCH_LIMIT]

    index_tickers = sorted({p.ticker for p in profile.index()})

    entries = []

    if index_tickers:
        if on_progress: on_progress("MARKET", "start")
        e = research_macro(index_tickers, brief=brief)
        entries.append(e)
        if on_progress: on_progress("MARKET", "ok" if e.ok else f"fail: {e.note[:40]}")
        _pace()

    for i, p in enumerate(conviction):
        if on_progress: on_progress(p.ticker, "start")
        sym = profile.symbol_for(p.ticker)
        e = research_brief(p.ticker, p.thesis, name=p.name, symbol=sym) if brief \
            else research_position_deep(p.ticker, p.thesis, name=p.name, symbol=sym)
        entries.append(e)
        if on_progress: on_progress(p.ticker, "ok" if e.ok else f"fail: {e.note[:40]}")
        if i < len(conviction) - 1:
            _pace()

    return entries


def _pace():
    if config.RESEARCH_PACE_SECONDS > 0:
        time.sleep(config.RESEARCH_PACE_SECONDS)


def _run(label: str, prompt: str, brief: bool) -> ResearchEntry:
    try:
        text = claude_client.ask_with_web_search(
            prompt, max_searches=config.RESEARCH_MAX_SEARCHES_PER_POSITION)
        if not text:
            return ResearchEntry(label, "", ok=False, note="empty response", brief=brief)
        return ResearchEntry(label, text, ok=True, brief=brief)
    except Exception as e:
        return ResearchEntry(label, "", ok=False,
                             note=f"{type(e).__name__}: {e}", brief=brief)
