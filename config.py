"""Central configuration — ENGINE settings only.

Personal portfolio specifics no longer live here. They are derived from
your PDF into state/profile.json (see core/profile.py) — holdings,
classification, thesis, symbol overrides, display currency, sandbox
accounts. This file is generic: a different user runs the same code with
their own profile, no edits here.

The one personal-ish knob kept here is DEFAULT_* values used only when
generating a fresh profile (you can change them per-profile afterwards).
"""

from pathlib import Path

# ─── Paths ───────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parent

INBOX_DIR = ROOT / "portfolio_inbox"
CURRENT_DIR = ROOT / "state" / "current"
PORTFOLIOS_DIR = ROOT / "state" / "portfolios"
OUTPUTS_HISTORY_DIR = ROOT / "state" / "outputs" / "history"

CURRENT_PDF = CURRENT_DIR / "portfolio.pdf"
PROFILE_PATH = ROOT / "state" / "profile.json"   # machine source of truth
PRICE_CACHE_PATH = ROOT / "state" / "price_cache.json"


# ─── Claude ──────────────────────────────────────────────────────────

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 8000
ENV_PATH = ROOT / ".secrets" / ".env"

# Rate-limit resilience: retry a 429'd call this many times, waiting
# RETRY_BASE_WAIT * attempt seconds between tries. Tier-1 is 30k input
# tokens/min, which web-search research can blow through — pacing + retry
# lets transient hits self-heal instead of landing "unavailable".
RETRY_MAX_ATTEMPTS = 3
RETRY_BASE_WAIT_SECONDS = 20
# A fixed pause between consecutive research calls, to stay under the
# per-minute token ceiling. 0 to disable.
RESEARCH_PACE_SECONDS = 5


# ─── Schedule ────────────────────────────────────────────────────────

DIGEST_CADENCE_DAYS = 7


# ─── Research ────────────────────────────────────────────────────────

RESEARCH_MAX_SEARCHES_PER_POSITION = 3

# Email body uses BRIEF research (one newsletter-style line per name).
# Deep multi-section research still exists and is available on demand via
# `make research T=TICKER`. False = long-form briefings in the email.
RESEARCH_BRIEF_FOR_EMAIL = True

# Only positions classified "conviction" are researched individually.
# "index" positions are covered by ONE shared macro briefing.
# "sandbox" positions are SKIPPED. Classification is set when the profile
# is generated (rule for sandbox accounts + extraction for index/conviction)
# and is editable in profile.json.

# Optional hard cap on conviction names researched per run (None = all).
# Handy while testing so runs are fast/cheap.
RESEARCH_LIMIT = None


# ─── Profile generation defaults ─────────────────────────────────────
# Used only when a NEW profile is generated from a PDF. Editable in the
# resulting profile.json afterwards.

DEFAULT_DISPLAY_CURRENCY = "CHF"
# Accounts whose holdings are your experimental sandbox — these positions
# are classified "sandbox" and skipped by research. Modular: a different
# user lists their own. Everything not in here is index or conviction,
# decided by extraction from the PDF.
DEFAULT_SANDBOX_ACCOUNTS = ["Trading 212"]

# Seed price-symbol overrides for tickers whose bare symbol won't resolve on
# the price source (foreign listings need an exchange suffix; commodities use
# a futures symbol). Written into a freshly generated profile so they're
# visible and editable in profile.json. Empty/missing = the bare ticker is
# used as-is. A different user edits this map (or just the JSON) for their own
# holdings. Note: Trading 212 holds foreign names via US/London depositary
# lines, NOT their home exchange — e.g. Samsung is the London USD GDR
# (SMSN.IL), not the Korea ordinary (005930.KS), which mispriced it ~23×.
DEFAULT_SYMBOL_OVERRIDES = {
    "VUAA": "VUAA.L",
    "SEC0": "SEC0.DE",
    "IS3N": "IS3N.DE",
    "WEXE": "WEXE.DE",
    "XAMZ": "XAMZ.DE",
    "LHL":  "0992.HK",
    "SMSN": "SMSN.IL",
    "GOLD": "GC=F",
    "SILVER": "SI=F",
}


# ─── FX ──────────────────────────────────────────────────────────────
# Convert all values to the profile's display currency for a single grand
# total, while still showing the native per-currency breakdown.
FX_ENABLE = True

# ─── Divergence guard ────────────────────────────────────────────────
# A live price can come back "successful" yet wrong — e.g. a holding priced
# off the wrong listing/share class (Trading 212's Samsung is a London USD
# GDR, not the Korea ordinary the override pointed at). The PDF-value
# fallback never catches this because the fetch didn't fail.
#
# But a large live-vs-PDF gap has two causes the snapshot can't distinguish:
# a structural mismatch (stable, e.g. 23x), OR a genuine price move (a real
# moonshot — the live price is RIGHT and the PDF is stale). So two tiers,
# both comparing in the display currency (max/min ratio):
#   FLAG   — gap >= this: keep the live value (might be a real move) but flag
#            the row for a human to verify. Ordinary drift stays under it.
#   REVERT — gap >= this: no holding organically moves this much between PDF
#            authorings, so the live price is almost certainly the wrong
#            instrument; revert to the PDF value and flag it.
# Set either to 0 to disable that tier.
DIVERGENCE_FLAG_FACTOR = 4.0
DIVERGENCE_REVERT_FACTOR = 8.0

# ─── Profile freshness ───────────────────────────────────────────────
# The REVERT tier above trusts the PDF value as ground truth — which only
# holds if the PDF is reasonably current. Past this age (days since the
# profile was generated from the PDF), the profile is treated as STALE:
#   - the revert tier is demoted to flag-only, so a possibly-years-old
#     value is never silently substituted into the total (a holding that
#     genuinely grew would otherwise be reverted DOWN to the stale value);
#   - the output carries a "supply a fresh portfolio" notice.
# 0 disables the staleness logic (revert tier always active).
PROFILE_STALE_AFTER_DAYS = 90

# ─── Wealth ──────────────────────────────────────────────────────────
# Include the non-investable "Additional wealth" section (cash, savings,
# bank) in the valuations output, and fold it into the grand total.
# False = investable holdings only; the summary line becomes "Total
# investable" instead of "Total wealth". Holdings are unaffected either way.
INCLUDE_WEALTH = True


