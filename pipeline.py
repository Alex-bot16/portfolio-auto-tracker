"""Pipeline — two flows, cleanly split.

accept_pdf()  (rare, when holdings change):
    portfolio_inbox/*.pdf -> promote to state/current/portfolio.pdf
    -> Claude extracts it ONCE into state/profile.json (the machine truth)

run_digest()  (every run, NO PDF/vision call):
    read profile.json -> live prices -> FX -> updated-values PDF (attachment)
                      -> research conviction (+macro), skip sandbox -> email body
                      -> save both -> send

Supplying a new PDF ALWAYS regenerates the profile wholesale. Hand-edits
to profile.json are allowed and are wiped on the next regeneration.
"""

from pathlib import Path

import config
from core import holdings, prices, research, digest, profile as profile_mod
from io_layer import intake, storage, send


def accept_pdf() -> str:
    """Promote newest inbox PDF to current, then extract it into profile.json.

    Returns the profile path. This is the one expensive (vision) step.
    """
    print("promoting newest PDF in portfolio_inbox/ ...")
    pdf_path = intake.accept_latest_pdf()
    print(f"  current PDF: {pdf_path}")

    print("extracting holdings into profile (Claude vision, one call)...")
    prof = holdings.extract_to_profile(pdf_path)
    profile_mod.save(prof)

    n_idx = len(prof.index()); n_con = len(prof.conviction()); n_sbx = len(prof.sandbox())
    print(f"  profile: {len(prof.positions)} positions "
          f"({n_con} conviction, {n_idx} index, {n_sbx} sandbox), "
          f"{len(prof.wealth)} wealth lines")
    print(f"  saved -> {config.PROFILE_PATH}")
    print("  (edit that file to correct anything; a new PDF will regenerate it)")
    return str(config.PROFILE_PATH)


def run_digest(do_research: bool = True, render_pdf: bool = True,
               use_price_cache: bool = True, send_email: bool = False,
               to: str | list | None = None) -> str:
    """Run one digest pass from the profile. Returns the run folder path.

    Builds + saves only by default. send_email=True also delivers it (this is
    `make full-digest`); otherwise send separately with `make send`.
    """
    try:
        prof = profile_mod.load()
    except FileNotFoundError:
        raise FileNotFoundError(
            f"No profile at {config.PROFILE_PATH}. "
            f"Drop a PDF in portfolio_inbox/ and run `make accept-pdf` first."
        )

    print(f"profile: {len(prof.positions)} positions "
          f"({len(prof.conviction())} conviction, {len(prof.index())} index, "
          f"{len(prof.sandbox())} sandbox), display {prof.display_currency}")

    age = prof.age_days()
    if config.PROFILE_STALE_AFTER_DAYS and age and age > config.PROFILE_STALE_AFTER_DAYS:
        print(f"  ⚠ this supplied portfolio is {age:.0f} days old — consider "
              f"supplying a new one (`make accept-pdf`)")

    print("1/4  fetching current prices...")
    ticker_symbol = {p.ticker: prof.symbol_for(p.ticker) for p in prof.positions}
    quotes = prices.fetch_quotes(ticker_symbol, use_cache=use_price_cache)
    ok = sum(1 for q in quotes.values() if q.ok)
    print(f"     {ok}/{len(ticker_symbol)} priced live "
          f"(rest fall back to PDF value)")

    print("2/4  building updated-values portfolio (+ FX total)...")
    valuations_md = digest.build_valuations_markdown(prof, quotes)

    if do_research:
        n_con = min(len(prof.conviction()),
                    config.RESEARCH_LIMIT or len(prof.conviction()))
        mode = "brief" if config.RESEARCH_BRIEF_FOR_EMAIL else "deep"
        print(f"3/4  researching {n_con} conviction names + macro ({mode}); "
              f"sandbox skipped...")

        def progress(label, status):
            if status == "start":
                print(f"     {label:8s} ...", end="", flush=True)
            else:
                print(f" {status}")

        entries = research.research_profile(prof, on_progress=progress)
    else:
        print("3/4  research skipped (do_research=False)")
        entries = []
    research_md = digest.build_research_markdown(entries)

    print("4/4  saving...")
    folder = storage.save_run(valuations_md, research_md, render_pdf=render_pdf)

    if send_email:
        send_run(folder, to=to)
    else:
        print("     (not sent — run `make send` or `make full-digest`)")

    print(f"done — {folder}")
    return str(folder)


def _latest_run_folder():
    if not config.OUTPUTS_HISTORY_DIR.exists():
        return None
    runs = sorted(p for p in config.OUTPUTS_HISTORY_DIR.glob("*_run") if p.is_dir())
    return runs[-1] if runs else None


def send_run(folder=None, to: str | list | None = None) -> str:
    """Send an existing run as an email — research.md is the body, the
    updated-values PDF the attachment. Rebuilds nothing; defaults to the
    latest run folder. `to` overrides recipients (else .secrets/.env)."""
    folder = Path(folder) if folder else _latest_run_folder()
    if folder is None or not Path(folder).is_dir():
        raise FileNotFoundError(
            "No run to send. Run `make digest` first (or pass a run folder)."
        )
    folder = Path(folder)
    body_path = folder / "research.md"
    if not body_path.exists():
        raise FileNotFoundError(f"No research.md in {folder} — nothing to send.")
    body = body_path.read_text(encoding="utf-8")
    pdf = folder / "portfolio_updated.pdf"
    attachment = pdf if pdf.exists() else None
    date = folder.name.split("T")[0]   # run folders are <ISO-timestamp>_run
    print(f"sending run {folder.name} ...")
    send.send(subject=f"Portfolio update — {date}",
              body_markdown=body, attachment_path=attachment, to=to)
    return str(folder)
