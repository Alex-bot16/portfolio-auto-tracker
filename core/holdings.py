"""Holdings — extract a PDF into a Profile (the machine source of truth).

This is the one expensive step (a Claude vision call). It runs when you
supply a new PDF via `make accept-pdf`, NOT on every digest. It produces
a fully-classified Profile and writes it to state/profile.json.

Classification precedence (decided):
  1. Rule: if a position's account is in sandbox_accounts -> "sandbox".
  2. Else: use the index/conviction tag Claude inferred from the PDF
     (your insights PDFs label the index "spine" vs conviction satellites).
  3. The resulting profile.json is hand-editable; edits are wiped on the
     next regeneration.
"""

import json
from pathlib import Path

import config
from core import claude_client
from core.profile import Profile, ProfilePosition, ProfileWealth, now_iso


_EXTRACT_PROMPT = """\
You are reading a personal investment portfolio PDF.

Return a JSON OBJECT with exactly two keys: "positions" and "wealth".

"positions" = INVESTABLE holdings (stocks, ETFs, commodities — anything
with a ticker and a share/unit count). Each object, these exact keys:

  "ticker"            — symbol (e.g. "AAPL","VUAA","OKLO"). Gold->"GOLD",
                        silver->"SILVER".
  "name"              — full name.
  "shares"            — number of shares/units (ounces for commodities).
  "account"           — account holding it, if shown. Else "".
  "currency"          — currency of the value shown for it. Else "".
  "pdf_value_native"  — value shown in the PDF, as a number. Null if absent.
  "pdf_gain_pct"      — ONLY the holding's total gain/loss SINCE PURCHASE,
                        as a number ("+5%" -> 5, "-3.2%" -> -3.2). It must be
                        unambiguous. Return null (do NOT guess) if ANY of:
                        - you can't tell whether a % is since-purchase vs a
                          daily/period change;
                        - more than one percentage sits near the holding and
                          it's unclear which is the return;
                        - the % is an allocation/weight, a dividend yield, or
                          any non-return figure;
                        - it's a portfolio- or section-level number, not THIS
                          holding's;
                        - it isn't in the same currency/basis as the holding's
                          value, or is unclear/garbled.
                        A null is SAFE — the holding just shows no gain. A
                        wrong number permanently corrupts its cost basis.
  "thesis"            — IF the PDF gives a thesis/catalyst/risk/commentary
                        for this holding, summarise in ONE line (<20 words).
                        Else "". Never invent one.
  "classification"    — your best read of its ROLE from the PDF:
                          "index"      = broad index/market tracker that
                                         forms the portfolio's core/"spine".
                          "conviction" = a single-name or thematic bet the
                                         investor holds with conviction.
                        Use the PDF's own language (e.g. a section called
                        "the spine", "core", "index" -> index; "conviction",
                        "satellite", individual stocks -> conviction). If
                        genuinely unclear, default to "conviction".

"wealth" = NON-investable buckets (cash, savings/money-market funds, gift
funds, bank balances — no ticker, not re-priced). Each object:

  "label","value_native","currency","account"

Rules:
- A holding with a ticker and shares is a POSITION, never wealth.
- Cash/savings/bank balances are WEALTH, never positions.
- Do NOT include subtotals, grand totals, or "total wealth" figures.
- Same ticker in multiple accounts -> one position object each.
- Output ONLY the JSON object. No prose, no markdown fences.
"""


def extract_to_profile(pdf_path: Path,
                       display_currency: str = None,
                       sandbox_accounts: list = None) -> Profile:
    """Read the PDF with Claude and build a fully-classified Profile.

    display_currency / sandbox_accounts default to config values; callers
    may override. The sandbox rule is applied here (account-based), then
    Claude's index/conviction tag is used for the rest.
    """
    display_currency = display_currency or config.DEFAULT_DISPLAY_CURRENCY
    sandbox_accounts = sandbox_accounts if sandbox_accounts is not None \
        else list(config.DEFAULT_SANDBOX_ACCOUNTS)

    raw = claude_client.ask_with_pdf(pdf_path, _EXTRACT_PROMPT)
    data = _parse_json_object(raw)

    positions = []
    for item in data.get("positions", []):
        account = item.get("account", "").strip()
        # Classification precedence: sandbox rule first, else extracted tag.
        if account in sandbox_accounts:
            classification = "sandbox"
        else:
            tag = item.get("classification", "").strip().lower()
            classification = tag if tag in ("index", "conviction") else "conviction"

        # Seed a price-symbol override from config (DEFAULT_SYMBOL_OVERRIDES);
        # the user can edit it in the JSON afterwards.
        ticker = item.get("ticker", "").strip().upper()
        positions.append(ProfilePosition(
            ticker=ticker,
            name=item.get("name", "").strip(),
            shares=float(item.get("shares", 0) or 0),
            account=account,
            currency=item.get("currency", "").strip(),
            classification=classification,
            thesis=item.get("thesis", "").strip(),
            symbol_override=config.DEFAULT_SYMBOL_OVERRIDES.get(ticker, ""),
            pdf_value_native=item.get("pdf_value_native"),
            pdf_gain_pct=_coerce_gain_pct(item.get("pdf_gain_pct")),
        ))

    wealth = []
    for item in data.get("wealth", []):
        val = item.get("value_native")
        if val is None:
            continue
        wealth.append(ProfileWealth(
            label=item.get("label", "").strip() or "Unlabelled",
            value_native=float(val),
            currency=item.get("currency", "").strip(),
            account=item.get("account", "").strip(),
        ))

    return Profile(
        display_currency=display_currency,
        sandbox_accounts=sandbox_accounts,
        positions=positions,
        wealth=wealth,
        generated_from=Path(pdf_path).name,
        generated_at=now_iso(),
    )


def _coerce_gain_pct(raw):
    """Void an ambiguous/invalid gain% rather than risk a wrong cost basis.
    Keeps a clean numeric value; discards anything non-numeric or impossible
    (<= -100%, which would imply a non-positive cost basis). A missing gain is
    safe (shows "—"); a wrong one permanently corrupts the cost basis."""
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return None
    return val if val > -100 else None


def _parse_json_object(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
        if text.endswith("```"):
            text = text[:-3].strip()
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Could not parse holdings JSON from Claude.\n"
            f"Error: {e}\nRaw response:\n{raw}"
        )
    if isinstance(obj, list):
        return {"positions": obj, "wealth": []}
    return obj
