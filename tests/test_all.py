"""Offline unit tests — no API key, no network, no PDF needed.

Run:  python -m tests.test_all   (or `make test`)

Covers the profile-driven architecture: profile save/load + classification
views, the PDF-value fallback, FX conversion to a display currency, the
single grand total, the conviction/index/sandbox research split + limit,
rate-limit retry logic, the price cache, intake, storage, and send.

Network-dependent paths (live prices, live FX, live research) are stubbed.
"""

import sys
import tempfile
import time
from pathlib import Path


class Runner:
    def __init__(self):
        self.passed = 0; self.failed = 0
    def section(self, name):
        print(f"\n{'=' * 64}\n  {name}\n{'=' * 64}")
    def check(self, label, cond, details=""):
        if cond:
            print(f"  ok   {label}"); self.passed += 1
        else:
            print(f"  FAIL {label}")
            if details: print(f"       {details}")
            self.failed += 1
    def summary(self):
        total = self.passed + self.failed
        print(f"\n{'=' * 64}\n  {self.passed}/{total} passed, {self.failed} failed\n{'=' * 64}\n")
        return 0 if self.failed == 0 else 1


r = Runner()

# ─── Imports ─────────────────────────────────────────────────────────
r.section("IMPORTS")
try:
    import config
    from core import fx, profile as profile_mod
    from core.profile import Profile, ProfilePosition, ProfileWealth
    from core.prices import Quote, fetch_quotes
    from core.research import ResearchEntry
    from core.digest import build_valuations_markdown, build_research_markdown
    from io_layer import intake, storage, send
    r.check("all modules import", True)
except Exception as e:
    r.check("all modules import", False, f"{type(e).__name__}: {e}")
    sys.exit(r.summary())

# ─── Config (engine-only; personal data gone) ───────────────────────
r.section("CONFIG: engine-only, personal data removed")
r.check("MODEL set", isinstance(config.MODEL, str) and bool(config.MODEL))
r.check("INDEX_TICKERS removed from config", not hasattr(config, "INDEX_TICKERS"))
r.check("PRICE_SYMBOLS removed from config", not hasattr(config, "PRICE_SYMBOLS"))
r.check("POSITION_THESES removed", not hasattr(config, "POSITION_THESES"))
r.check("DEFAULT_DISPLAY_CURRENCY present", hasattr(config, "DEFAULT_DISPLAY_CURRENCY"))
r.check("DEFAULT_SANDBOX_ACCOUNTS is a list", isinstance(config.DEFAULT_SANDBOX_ACCOUNTS, list))
r.check("RETRY_MAX_ATTEMPTS is int", isinstance(config.RETRY_MAX_ATTEMPTS, int))
r.check("FX_ENABLE is bool", isinstance(config.FX_ENABLE, bool))

# ─── Profile model + views ───────────────────────────────────────────
r.section("PROFILE: models + classification views")
prof = Profile(
    display_currency="CHF",
    sandbox_accounts=["Trading 212"],
    positions=[
        ProfilePosition("VUAA", "Vanguard S&P 500", 10, "Revolut", "USD", "index"),
        ProfilePosition("OKLO", "Oklo", 5, "Revolut", "USD", "conviction", thesis="nuclear"),
        ProfilePosition("KOPN", "Kopin", 5, "Trading 212", "USD", "sandbox"),
        ProfilePosition("SMSN", "Samsung", 1, "Trading 212", "CHF", "sandbox",
                        symbol_override="005930.KS", pdf_value_native=18.64),
    ],
    wealth=[ProfileWealth("Cash", 7146.0, "CHF", "Revolut")],
)
r.check("conviction() filters", [p.ticker for p in prof.conviction()] == ["OKLO"])
r.check("index() filters", [p.ticker for p in prof.index()] == ["VUAA"])
r.check("sandbox() filters", {p.ticker for p in prof.sandbox()} == {"KOPN", "SMSN"})
r.check("symbol_for override wins", prof.symbol_for("SMSN") == "005930.KS")
r.check("symbol_for falls back to bare ticker", prof.symbol_for("OKLO") == "OKLO")
r.check("tickers() dedups+sorts", prof.tickers() == ["KOPN", "OKLO", "SMSN", "VUAA"])

# ─── Profile save / load round-trip ──────────────────────────────────
r.section("PROFILE: save/load round-trip")
with tempfile.TemporaryDirectory() as tmp:
    p = Path(tmp) / "profile.json"
    profile_mod.save(prof, p)
    loaded = profile_mod.load(p)
    r.check("round-trips position count", len(loaded.positions) == 4)
    r.check("round-trips classification", loaded.sandbox()[0].classification == "sandbox")
    r.check("round-trips display currency", loaded.display_currency == "CHF")
    r.check("round-trips sandbox_accounts", loaded.sandbox_accounts == ["Trading 212"])
    r.check("round-trips pdf fallback value",
            any(x.pdf_value_native == 18.64 for x in loaded.positions))
    r.check("round-trips wealth", loaded.wealth[0].value_native == 7146.0)

# ─── FX conversion ───────────────────────────────────────────────────
r.section("FX: conversion + soft failure")
fx._cache.clear()
fx._cache[("USD", "CHF")] = fx.Rate("USDCHF=X", 0.80, True)
fx._cache[("EUR", "CHF")] = fx.Rate("EURCHF=X", 0.95, True)
fx._cache[("XXX", "CHF")] = fx.Rate("XXXCHF=X", 0.0, False, "no rate")
v, ok = fx.to_display(100.0, "USD", "CHF")
r.check("USD->CHF converts", ok and abs(v - 80.0) < 1e-9)
v, ok = fx.to_display(100.0, "CHF", "CHF")
r.check("same-currency is identity, rate 1.0", ok and v == 100.0)
v, ok = fx.to_display(100.0, "XXX", "CHF")
r.check("unobtainable rate fails soft (0,False)", (not ok) and v == 0.0)
v, ok = fx.to_display(100.0, "", "CHF")
r.check("empty currency fails soft", not ok)

# ─── Valuations: live / PDF-fallback / unavailable + FX total ───────
r.section("VALUATIONS: fallback, coverage, native breakdown, FX total")
fx._cache.clear()
fx._cache[("USD", "CHF")] = fx.Rate("USDCHF=X", 0.80, True)
fx._cache[("CHF", "CHF")] = fx.Rate("", 1.0, True)
vprof = Profile(
    display_currency="CHF", sandbox_accounts=["Trading 212"],
    positions=[
        ProfilePosition("AAPL", "Apple", 10, "Revolut", "USD", "conviction"),       # live
        ProfilePosition("SMSN", "Samsung", 1, "Trading 212", "CHF", "sandbox",
                        pdf_value_native=18.64),                                     # PDF fallback
        ProfilePosition("ZZZ", "Mystery", 2, "Trading 212", "", "sandbox"),         # unavailable
    ],
    wealth=[ProfileWealth("Cash", 1000.0, "CHF", "Revolut")],
)
quotes = {
    "AAPL": Quote("AAPL", "AAPL", 250.0, "USD", True),
    "SMSN": Quote("SMSN", "005930.KS", 0.0, "", False, "no price"),
    "ZZZ":  Quote("ZZZ", "ZZZ", 0.0, "", False, "no price"),
}
vmd = build_valuations_markdown(vprof, quotes)
r.check("live value computed (250*10)", "2,500.00 USD" in vmd)
r.check("failed ticker w/ pdf value falls back", "18.64 CHF" in vmd)
r.check("fallback tagged source PDF", "| PDF |" in vmd)
r.check("unpriceable w/o pdf shows 'unavailable'", "unavailable" in vmd)
r.check("NO raw error leaks", "TypeError" not in vmd and "Traceback" not in vmd)
r.check("coverage counts reported", "priced live" in vmd and "from PDF value" in vmd)
r.check("native breakdown present", "native breakdown" in vmd)
r.check("investable CHF total present (2500*0.8=2000 + 18.64)",
        "2,018.64 CHF" in vmd)
r.check("wealth section present", "Additional wealth" in vmd)
r.check("grand total line present", "Total wealth" in vmd)
# grand total = investable 2018.64 + wealth 1000 = 3018.64
r.check("grand total sums investable+wealth", "3,018.64 CHF" in vmd)

# FX disabled path
_fx_was = config.FX_ENABLE
try:
    config.FX_ENABLE = False
    vmd_nofx = build_valuations_markdown(vprof, quotes)
    r.check("FX off: no grand total", "Total wealth" not in vmd_nofx)
    r.check("FX off: native breakdown still shown", "native breakdown" in vmd_nofx)
finally:
    config.FX_ENABLE = _fx_was

# ─── Divergence guard (two tiers) ────────────────────────────────────
r.section("DIVERGENCE GUARD: flag vs revert")
fx._cache.clear()
fx._cache[("USD", "CHF")] = fx.Rate("USDCHF=X", 0.80, True)
fx._cache[("KRW", "CHF")] = fx.Rate("KRWCHF=X", 0.00052, True)
fx._cache[("CHF", "CHF")] = fx.Rate("", 1.0, True)
gprof = Profile(
    display_currency="CHF", sandbox_accounts=["Trading 212"],
    positions=[
        # ~23x off: live prices the wrong instrument -> revert to PDF value
        ProfilePosition("SMSN", "Samsung", 0.00461632, "Trading 212", "CHF",
                        "sandbox", symbol_override="005930.KS", pdf_value_native=18.64),
        # ~5x up: plausibly a real move -> keep the live value, just flag it
        ProfilePosition("MOON", "Moonshot", 1, "Revolut", "USD",
                        "conviction", pdf_value_native=100.0),
    ],
    wealth=[],
)
gquotes = {
    "SMSN": Quote("SMSN", "005930.KS", 340500.0, "KRW", True),   # live but wrong instrument
    "MOON": Quote("MOON", "MOON", 500.0, "USD", True),           # genuinely 5x
}
gmd = build_valuations_markdown(gprof, gquotes)
r.check("revert tier: uses PDF value", "18.64 CHF" in gmd)
r.check("revert tier: row tagged 'PDF (live'", "PDF (live" in gmd)
r.check("revert tier: wrong live value dropped", "0.82" not in gmd)
r.check("revert tier: coverage shows reverted", "reverted to PDF" in gmd)
r.check("flag tier: keeps live value (500 USD)", "500.00 USD" in gmd)
r.check("flag tier: row tagged 'live ⚠'", "live ⚠" in gmd)
r.check("flag tier: coverage shows flagged", "live but flagged" in gmd)

# ─── Profile staleness gates the revert tier ─────────────────────────
r.section("STALENESS: old PDF demotes revert -> flag + notice")
fx._cache.clear()
fx._cache[("USD", "CHF")] = fx.Rate("USDCHF=X", 0.80, True)   # used by later sections
fx._cache[("KRW", "CHF")] = fx.Rate("KRWCHF=X", 0.00052, True)
fx._cache[("CHF", "CHF")] = fx.Rate("", 1.0, True)
sprof = Profile(
    display_currency="CHF", sandbox_accounts=["Trading 212"],
    positions=[
        ProfilePosition("SMSN", "Samsung", 0.00461632, "Trading 212", "CHF",
                        "sandbox", symbol_override="005930.KS", pdf_value_native=18.64),
    ],
    wealth=[], generated_at="2020-01-01T00:00:00Z",   # years old -> stale
)
squotes = {"SMSN": Quote("SMSN", "005930.KS", 340500.0, "KRW", True)}
smd = build_valuations_markdown(sprof, squotes)
r.check("age_days computed for valid timestamp", (sprof.age_days() or 0) > 1000)
r.check("age_days None when timestamp missing", Profile("CHF", [], [], []).age_days() is None)
r.check("stale: 'days old' notice shown", "days old" in smd)
r.check("stale: notice nudges a fresh PDF", "accept-pdf" in smd)
r.check("stale: revert demoted to flag (live kept)", "live ⚠" in smd)
r.check("stale: NOT reverted to PDF", "PDF (live" not in smd)
r.check("fresh profile shows no stale notice", "days old" not in gmd)

# ─── INCLUDE_WEALTH toggle ───────────────────────────────────────────
r.section("INCLUDE_WEALTH toggle")
_w_was = config.INCLUDE_WEALTH
try:
    config.INCLUDE_WEALTH = True
    on = build_valuations_markdown(vprof, quotes)
    r.check("wealth ON: section shown", "Additional wealth" in on)
    r.check("wealth ON: total labelled 'Total wealth'", "Total wealth" in on)
    r.check("wealth ON: total includes wealth (3,018.64)", "3,018.64 CHF" in on)

    config.INCLUDE_WEALTH = False
    off = build_valuations_markdown(vprof, quotes)
    r.check("wealth OFF: section hidden", "Additional wealth" not in off)
    r.check("wealth OFF: relabelled 'Total investable'", "Total investable" in off)
    r.check("wealth OFF: no 'Total wealth'", "Total wealth" not in off)
    r.check("wealth OFF: total is investable-only (2,018.64)", "2,018.64 CHF" in off)
    r.check("wealth OFF: investable holdings still present", "Investable holdings" in off)
finally:
    config.INCLUDE_WEALTH = _w_was

# ─── Cost-basis running gain% ────────────────────────────────────────
r.section("GAIN%: running return vs PDF-implied cost basis")
from core.digest import _cost_basis_native
r.check("cost basis 105 @ +5% -> 100",
        abs(_cost_basis_native(ProfilePosition("X", "x", 1, pdf_value_native=105, pdf_gain_pct=5)) - 100.0) < 1e-9)
r.check("cost basis 80 @ -20% -> 100",
        abs(_cost_basis_native(ProfilePosition("X", "x", 1, pdf_value_native=80, pdf_gain_pct=-20)) - 100.0) < 1e-9)
r.check("cost basis None without gain%",
        _cost_basis_native(ProfilePosition("X", "x", 1, pdf_value_native=105)) is None)
r.check("cost basis None at -100% (no div0)",
        _cost_basis_native(ProfilePosition("X", "x", 1, pdf_value_native=105, pdf_gain_pct=-100)) is None)
fx._cache.clear()
fx._cache[("USD", "CHF")] = fx.Rate("USDCHF=X", 1.0, True)
fx._cache[("CHF", "CHF")] = fx.Rate("", 1.0, True)
gnprof = Profile(
    display_currency="CHF", sandbox_accounts=[],
    positions=[   # PDF showed 105 at +5% -> bought at 100; live 110 -> +10%
        ProfilePosition("STK", "Stock", 1, "Revolut", "USD", "conviction",
                        pdf_value_native=105.0, pdf_gain_pct=5.0),
    ],
    wealth=[],
)
gnmd = build_valuations_markdown(gnprof, {"STK": Quote("STK", "STK", 110.0, "USD", True)})
r.check("Gain % column present", "Gain %" in gnmd)
r.check("running gain computed (+10.0%)", "+10.0%" in gnmd)
r.check("portfolio total gain vs cost shown", "total gain vs cost: +10.0%" in gnmd)

# Void ambiguous/invalid gain% at extraction (a wrong cost basis is worse).
from core.holdings import _coerce_gain_pct
r.check("coerce keeps a valid number", _coerce_gain_pct(5) == 5.0)
r.check("coerce keeps a valid loss", _coerce_gain_pct(-50) == -50.0)
r.check("coerce voids non-numeric", _coerce_gain_pct("n/a") is None)
r.check("coerce voids None", _coerce_gain_pct(None) is None)
r.check("coerce voids impossible -100%", _coerce_gain_pct(-100) is None)
r.check("coerce voids impossible <-100%", _coerce_gain_pct(-150) is None)
r.check("cost basis voids non-numeric gain (hand-edited JSON)",
        _cost_basis_native(ProfilePosition("X", "x", 1, pdf_value_native=100, pdf_gain_pct="oops")) is None)

# ─── Research split (conviction / index / sandbox) ──────────────────
r.section("RESEARCH: conviction-only, index->macro, sandbox skipped")
import core.research as rm
calls = {"brief": [], "deep": [], "macro": []}
def fake_brief(t, th="", name="", symbol=""): calls["brief"].append(t); return ResearchEntry(t, "x", brief=True)
def fake_deep(t, th="", name="", symbol=""):  calls["deep"].append(t);  return ResearchEntry(t, "x")
def fake_macro(ix, brief=True): calls["macro"].append(tuple(ix)); return ResearchEntry("MARKET", "x", brief=brief)
orig = (rm.research_brief, rm.research_position_deep, rm.research_macro)
orig_cfg = (config.RESEARCH_BRIEF_FOR_EMAIL, config.RESEARCH_LIMIT, config.RESEARCH_PACE_SECONDS)
try:
    rm.research_brief, rm.research_position_deep, rm.research_macro = fake_brief, fake_deep, fake_macro
    config.RESEARCH_BRIEF_FOR_EMAIL = True
    config.RESEARCH_LIMIT = None
    config.RESEARCH_PACE_SECONDS = 0  # no sleeping in tests
    rprof = Profile(
        display_currency="CHF", sandbox_accounts=["Trading 212"],
        positions=[
            ProfilePosition("VUAA", "S&P 500", 10, "Revolut", "USD", "index"),
            ProfilePosition("WEXE", "World exUS", 5, "Revolut", "EUR", "index"),
            ProfilePosition("OKLO", "Oklo", 5, "Revolut", "USD", "conviction", thesis="nuclear"),
            ProfilePosition("OKLO", "Oklo", 2, "Revolut", "USD", "conviction"),  # dup
            ProfilePosition("META", "Meta", 3, "Revolut", "USD", "conviction"),
            ProfilePosition("KOPN", "Kopin", 5, "Trading 212", "USD", "sandbox"),
            ProfilePosition("PLTR", "Palantir", 1, "Trading 212", "USD", "sandbox"),
        ],
        wealth=[],
    )
    seen = []
    entries = rm.research_profile(rprof, on_progress=lambda l, s: seen.append((l, s)))
    r.check("macro called once (index funds)", len(calls["macro"]) == 1)
    r.check("macro got both index tickers", set(calls["macro"][0]) == {"VUAA", "WEXE"})
    r.check("brief used (not deep)", calls["deep"] == [])
    r.check("conviction researched", set(calls["brief"]) == {"OKLO", "META"})
    r.check("dup conviction researched once", calls["brief"].count("OKLO") == 1)
    r.check("sandbox NOT researched", "KOPN" not in calls["brief"] and "PLTR" not in calls["brief"])
    r.check("macro entry first", entries[0].label == "MARKET")
    r.check("progress callback fired", len(seen) >= 4)

    # limit caps conviction
    calls["brief"].clear()
    config.RESEARCH_LIMIT = 1
    rm.research_profile(rprof)
    r.check("RESEARCH_LIMIT caps conviction", len(calls["brief"]) == 1)
finally:
    rm.research_brief, rm.research_position_deep, rm.research_macro = orig
    (config.RESEARCH_BRIEF_FOR_EMAIL, config.RESEARCH_LIMIT, config.RESEARCH_PACE_SECONDS) = orig_cfg

# ─── Research markdown (email body) ──────────────────────────────────
r.section("RESEARCH MARKDOWN")
entries = [
    ResearchEntry("MARKET", "- macro ([s](http://x))", brief=True),
    ResearchEntry("OKLO", "- **OKLO** — milestone ([s](http://y))", brief=True),
    ResearchEntry("ASTS", "", ok=False, note="no news", brief=True),
]
rmd = build_research_markdown(entries)
r.check("has research header", "Portfolio Research" in rmd)
r.check("has market backdrop section", "Market backdrop" in rmd)
r.check("has conviction section", "Conviction positions" in rmd)
r.check("brief failed entry inline", "_unavailable: no news_" in rmd)
r.check("empty research handled", "No research run" in build_research_markdown([]))

# ─── Rate-limit retry logic ──────────────────────────────────────────
r.section("RATE-LIMIT: retry detection + backoff")
import core.claude_client as cc
r.check("detects RateLimitError by name",
        cc._is_rate_limit(type("RateLimitError", (Exception,), {})()))
r.check("detects 429 in message", cc._is_rate_limit(Exception("Error code: 429")))
r.check("detects rate_limit string", cc._is_rate_limit(Exception("rate_limit_error")))
r.check("ignores unrelated error", not cc._is_rate_limit(ValueError("bad json")))
# retry actually retries then re-raises, without real network
attempts = {"n": 0}
class _RL(Exception): pass
def boom(**kw):
    attempts["n"] += 1
    raise _RL("429 rate_limit_error")
_orig_sleep = time.sleep
_orig_create = cc._client.messages.create
_orig_attempts, _orig_wait = config.RETRY_MAX_ATTEMPTS, config.RETRY_BASE_WAIT_SECONDS
try:
    time.sleep = lambda s: None       # don't actually wait
    cc._client.messages.create = boom
    config.RETRY_MAX_ATTEMPTS = 3
    config.RETRY_BASE_WAIT_SECONDS = 0
    raised = False
    try:
        cc._create_with_retry(model="m", max_tokens=10, messages=[])
    except _RL:
        raised = True
    r.check("retries up to RETRY_MAX_ATTEMPTS", attempts["n"] == 3)
    r.check("re-raises after exhausting retries", raised)
finally:
    time.sleep = _orig_sleep
    cc._client.messages.create = _orig_create
    config.RETRY_MAX_ATTEMPTS, config.RETRY_BASE_WAIT_SECONDS = _orig_attempts, _orig_wait

# ─── Price cache ─────────────────────────────────────────────────────
r.section("PRICE CACHE: TTL reuse")
import core.prices as pr
with tempfile.TemporaryDirectory() as tmp:
    saved = config.PRICE_CACHE_PATH
    fetch_calls = {"n": 0}
    orig_fetch = pr._fetch_one
    try:
        config.PRICE_CACHE_PATH = Path(tmp) / "price_cache.json"
        def counting_fetch(ticker, symbol):
            fetch_calls["n"] += 1
            return Quote(ticker, symbol, 100.0, "USD", True)
        pr._fetch_one = counting_fetch
        # first call: cache miss -> fetch
        q1 = fetch_quotes({"AAPL": "AAPL"}, use_cache=True, ttl_seconds=3600)
        r.check("first fetch hits network", fetch_calls["n"] == 1 and q1["AAPL"].ok)
        # second call within TTL: cache hit -> no fetch
        q2 = fetch_quotes({"AAPL": "AAPL"}, use_cache=True, ttl_seconds=3600)
        r.check("second fetch served from cache", fetch_calls["n"] == 1)
        r.check("cached quote noted as cache", q2["AAPL"].note == "cache")
        # TTL 0: always refetch
        fetch_quotes({"AAPL": "AAPL"}, use_cache=True, ttl_seconds=0)
        r.check("ttl=0 forces refetch", fetch_calls["n"] == 2)
        # use_cache=False: always fetch
        fetch_quotes({"AAPL": "AAPL"}, use_cache=False)
        r.check("use_cache=False bypasses cache", fetch_calls["n"] == 3)
    finally:
        pr._fetch_one = orig_fetch
        config.PRICE_CACHE_PATH = saved

# ─── Intake ──────────────────────────────────────────────────────────
r.section("INTAKE")
with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    saved = (config.INBOX_DIR, config.CURRENT_DIR, config.CURRENT_PDF, config.PORTFOLIOS_DIR)
    try:
        config.INBOX_DIR = tmp / "inbox"; config.CURRENT_DIR = tmp / "current"
        config.CURRENT_PDF = config.CURRENT_DIR / "portfolio.pdf"
        config.PORTFOLIOS_DIR = tmp / "portfolios"; config.INBOX_DIR.mkdir(parents=True)
        raised = False
        try: intake.accept_latest_pdf()
        except FileNotFoundError: raised = True
        r.check("raises when inbox empty", raised)
        (config.INBOX_DIR / "p1.pdf").write_bytes(b"%PDF one")
        res = intake.accept_latest_pdf()
        r.check("promotes to current", res.read_bytes() == b"%PDF one")
        (config.INBOX_DIR / "p2.pdf").write_bytes(b"%PDF two")
        intake.accept_latest_pdf()
        r.check("second promoted", config.CURRENT_PDF.read_bytes() == b"%PDF two")
        r.check("prior archived", len(list(config.PORTFOLIOS_DIR.glob("*.pdf"))) == 1)
    finally:
        (config.INBOX_DIR, config.CURRENT_DIR, config.CURRENT_PDF, config.PORTFOLIOS_DIR) = saved

# ─── Storage ─────────────────────────────────────────────────────────
r.section("STORAGE")
with tempfile.TemporaryDirectory() as tmp:
    saved = config.OUTPUTS_HISTORY_DIR
    try:
        config.OUTPUTS_HISTORY_DIR = Path(tmp) / "history"
        folder = storage.save_run("# vals\n", "# research\n", render_pdf=False)
        r.check("writes portfolio_updated.md", (folder / "portfolio_updated.md").exists())
        r.check("writes research.md", (folder / "research.md").exists())
        r.check("no PDF when render off", not (folder / "portfolio_updated.pdf").exists())
    finally:
        config.OUTPUTS_HISTORY_DIR = saved

# ─── Send ────────────────────────────────────────────────────────────
r.section("SEND")
try:
    send.send("Subj", "# body", attachment_path=None)
    r.check("stub send runs", True)
except Exception as e:
    r.check("stub send runs", False, str(e))
r.check("ACTIVE_SENDER implements Sender", isinstance(send.ACTIVE_SENDER, send.Sender))

sys.exit(r.summary())
