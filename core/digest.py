"""Digest — build the two outputs of a run, from the profile + live prices.

  build_valuations_markdown()  -> "where you stand": investable holdings
     (live price, else PDF-value fallback), an additional-wealth section,
     a native per-currency breakdown AND a single FX-converted grand total
     in the profile's display currency. Rendered to the PDF attachment.
  build_research_markdown()    -> per-ticker (+ macro) research. Email body.

Value per holding: live_price*shares if priced, else PDF value, else
flagged "unavailable" (never an error). Every value is also converted to
the display currency for the grand total; unconvertible ones are excluded
and counted so the total is never silently wrong.
"""

from dataclasses import dataclass
from datetime import datetime, timezone

import config
from core import fx
from core.profile import Profile, ProfilePosition, ProfileWealth
from core.prices import Quote
from core.research import ResearchEntry


def _cost_basis_native(p: ProfilePosition):
    """Implied purchase value in the PDF's currency, from the PDF value and its
    stated gain%: value / (1 + gain%/100). None if either input is missing or
    the gain implies a non-positive basis (e.g. -100%)."""
    if p.pdf_value_native is None or p.pdf_gain_pct is None:
        return None
    try:
        pct = float(p.pdf_gain_pct)
        base = float(p.pdf_value_native)
    except (TypeError, ValueError):
        return None
    denom = 1.0 + pct / 100.0
    if denom <= 0:
        return None
    return base / denom


def _divergence_ratio(live_value, live_ccy, pdf_value, pdf_ccy, disp):
    """How far live and PDF values disagree, as a max/min ratio in the display
    currency. None if either side can't be converted or is non-positive."""
    lv, ok1 = fx.to_display(live_value, live_ccy, disp)
    pv, ok2 = fx.to_display(pdf_value, pdf_ccy, disp)
    if not (ok1 and ok2) or lv <= 0 or pv <= 0:
        return None
    return max(lv / pv, pv / lv)


def _resolve_value(p: ProfilePosition, q: Quote, disp: str,
                   flag_factor: float, revert_factor: float):
    """Return (price_str, value, currency, source).

    Divergence guard (two tiers, comparing live vs PDF in the display
    currency). A live price can succeed yet be wrong (wrong listing/class),
    but a large gap might equally be a genuine price move. So:
      - gap >= revert_factor: almost certainly the wrong instrument — revert
        to the PDF value and tag it "PDF (live N× off)".
      - gap >= flag_factor:   keep the live value (could be a real move) but
        tag it "live ⚠ N× vs PDF" so a human can verify.
    """
    if q and q.ok:
        live_value = q.price * p.shares
        ratio = None
        if p.pdf_value_native is not None:
            ratio = _divergence_ratio(live_value, q.currency,
                                      float(p.pdf_value_native), p.currency, disp)
        if ratio is not None and revert_factor and ratio >= revert_factor:
            return ("—", float(p.pdf_value_native), (p.currency or ""),
                    f"PDF (live {ratio:.0f}× off)")
        price_str = f"{q.price:,.2f} {q.currency}"
        if ratio is not None and flag_factor and ratio >= flag_factor:
            return price_str, live_value, q.currency, f"live ⚠ {ratio:.0f}× vs PDF"
        return price_str, live_value, q.currency, "live"
    if p.pdf_value_native is not None:
        return "—", float(p.pdf_value_native), (p.currency or ""), "PDF"
    return "—", 0.0, "", "unavailable"


def build_valuations_markdown(profile: Profile, quotes: dict) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    disp = profile.display_currency
    use_fx = config.FX_ENABLE

    # Staleness: an old PDF can't be trusted as the divergence guard's
    # oracle, so past the configured age we demote the revert tier to
    # flag-only and surface a "supply a fresh portfolio" notice.
    age = profile.age_days()
    max_age = config.PROFILE_STALE_AFTER_DAYS
    stale = bool(max_age and age is not None and age > max_age)
    revert_factor = 0.0 if stale else config.DIVERGENCE_REVERT_FACTOR

    lines = [f"# Portfolio — updated {now}\n"]
    if stale:
        lines.append(
            f"> ⚠️ **This supplied portfolio is {age:.0f} days old** "
            f"(last refreshed {profile.generated_at[:10]}). Consider supplying a "
            f"fresh PDF and running `make accept-pdf` — figures may be stale. "
            f"While stale, live prices that diverge from the PDF are flagged for "
            f"review, **not** auto-reverted to the old value.\n"
        )

    # ── Investable holdings ──────────────────────────────────────────
    lines.append("## Investable holdings\n")
    lines.append(f"| Holding | Ticker | Account | Shares | Price | Value | {disp} | Gain % | Source |")
    lines.append("|---|---|---|---:|---:|---:|---:|---:|---|")

    native_totals = {}          # currency -> sum
    grand_disp = 0.0            # sum in display currency
    unconverted = []            # currencies we couldn't convert
    gain_cur_disp = gain_base_disp = 0.0   # for portfolio-level gain vs cost
    live_n = pdf_n = flagged_n = reverted_n = unavail_n = 0

    for p in profile.positions:
        q = quotes.get(p.ticker)
        price_str, value, ccy, source = _resolve_value(
            p, q, disp, config.DIVERGENCE_FLAG_FACTOR, revert_factor)
        value_str = f"{value:,.2f} {ccy}".strip() if source != "unavailable" else "unavailable"

        disp_str = "—"
        if source != "unavailable" and ccy:
            native_totals[ccy] = native_totals.get(ccy, 0.0) + value
            if use_fx:
                conv, ok = fx.to_display(value, ccy, disp)
                if ok:
                    grand_disp += conv
                    disp_str = f"{conv:,.2f}"
                else:
                    unconverted.append(ccy)

        # Running gain vs the cost basis implied by the PDF (value + gain%).
        # Computed in the display currency so every holding gets a figure;
        # for same-currency holdings this equals the pure price gain.
        gain_str = "—"
        cb = _cost_basis_native(p)
        if cb and cb > 0 and source != "unavailable":
            cur_d, ok1 = fx.to_display(value, ccy, disp)
            base_d, ok2 = fx.to_display(cb, p.currency, disp)
            if ok1 and ok2 and base_d > 0:
                gain_str = f"{(cur_d / base_d - 1) * 100:+.1f}%"
                gain_cur_disp += cur_d
                gain_base_disp += base_d

        if source == "live": live_n += 1
        elif source.startswith("live"): flagged_n += 1
        elif source == "PDF": pdf_n += 1
        elif source.startswith("PDF (live"): reverted_n += 1
        else: unavail_n += 1

        acct = p.account or "—"
        lines.append(
            f"| {p.name} | {p.ticker} | {acct} | {p.shares:g} | "
            f"{price_str} | {value_str} | {disp_str} | {gain_str} | {source} |"
        )

    lines.append("")
    if native_totals:
        nat = " · ".join(f"{v:,.2f} {c}" for c, v in sorted(native_totals.items()))
        lines.append(f"**Investable — native breakdown:** {nat}")
    if use_fx:
        lines.append(f"**Investable — total in {disp}: {grand_disp:,.2f} {disp}**")
        if unconverted:
            uniq = ", ".join(sorted(set(unconverted)))
            lines.append(f"_(excludes unconvertible currencies: {uniq})_")
    if gain_base_disp > 0:
        tot_gain = (gain_cur_disp / gain_base_disp - 1) * 100
        lines.append(f"**Investable — total gain vs cost: {tot_gain:+.1f}%** "
                     f"_(holdings with a PDF gain%; cost basis from the PDF)_")
    cov = f"_{live_n} priced live"
    if flagged_n:
        cov += f", {flagged_n} live but flagged (diverges from PDF — verify)"
    cov += f", {pdf_n} from PDF value"
    if reverted_n:
        cov += f", {reverted_n} reverted to PDF (live price implausible)"
    cov += f", {unavail_n} unavailable._\n"
    lines.append(cov)

    # ── Additional wealth ────────────────────────────────────────────
    # Shown only when INCLUDE_WEALTH is on. Off => investable holdings only,
    # and the summary total below reports the investable slice alone.
    wealth_disp_total = 0.0
    show_wealth = config.INCLUDE_WEALTH and bool(profile.wealth)
    if show_wealth:
        lines.append("## Additional wealth (cash, savings, bank)\n")
        lines.append(f"| Bucket | Account | Value | {disp} |")
        lines.append("|---|---|---:|---:|")
        wealth_native = {}
        for w in profile.wealth:
            ccy = w.currency or ""
            disp_str = "—"
            if ccy:
                wealth_native[ccy] = wealth_native.get(ccy, 0.0) + w.value_native
                if use_fx:
                    conv, ok = fx.to_display(w.value_native, ccy, disp)
                    if ok:
                        wealth_disp_total += conv
                        disp_str = f"{conv:,.2f}"
            acct = w.account or "—"
            lines.append(f"| {w.label} | {acct} | {w.value_native:,.2f} {ccy} | {disp_str} |")
        lines.append("")
        if wealth_native:
            wn = " · ".join(f"{v:,.2f} {c}" for c, v in sorted(wealth_native.items()))
            lines.append(f"**Additional wealth — native breakdown:** {wn}")
        if use_fx:
            lines.append(f"**Additional wealth — total in {disp}: {wealth_disp_total:,.2f} {disp}**")
        lines.append("")

    # ── Summary total ────────────────────────────────────────────────
    # With wealth: true net worth. Without: investable slice only, relabelled.
    if use_fx:
        if show_wealth:
            total = grand_disp + wealth_disp_total
            lines.append(f"## Total wealth ≈ {total:,.2f} {disp}\n")
            lines.append(
                f"_Investable {grand_disp:,.2f} + additional {wealth_disp_total:,.2f} {disp}. "
                f"FX-converted from native currencies at current rates; treat as "
                f"approximate._\n"
            )
        else:
            lines.append(f"## Total investable ≈ {grand_disp:,.2f} {disp}\n")
            lines.append(
                f"_Investable holdings only; cash, savings and bank balances "
                f"are excluded. FX-converted from native currencies at current "
                f"rates; treat as approximate._\n"
            )

    note = (
        "_Investable values use live prices where available, otherwise the "
        "value stated in your supplied PDF."
    )
    if show_wealth:
        note += " Additional-wealth lines are taken from the PDF as-is."
    note += "_\n"
    lines.append(note)
    lines.append("\n---\n_For personal reference only. Not financial advice._")
    return "\n".join(lines)


def build_research_markdown(research: list) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"# Portfolio Research — {now}\n"]
    lines.append(
        "_Updated portfolio values are attached as a PDF. Below is fresh "
        "research per conviction position, plus the macro backdrop for your "
        "index holdings._\n"
    )
    if not research:
        lines.append("_No research run this cycle._")
        return "\n".join(lines)

    macro = [e for e in research if e.label == "MARKET"]
    names = [e for e in research if e.label != "MARKET"]

    if macro:
        lines.append("## Market backdrop (index holdings)\n")
        lines.append(macro[0].as_markdown())
        lines.append("")
    if names:
        lines.append("## Conviction positions\n")
        for e in names:
            lines.append(e.as_markdown())
        lines.append("")
    lines.append("\n---\n_For personal reference only. Not financial advice._")
    return "\n".join(lines)
