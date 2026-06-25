"""Profile — the machine source of truth, derived from the PDF.

The PDF is what YOU author (in Claude.ai). The profile is what the MACHINE
reads. Supplying a new PDF regenerates the profile wholesale via Claude
(see holdings.extract_to_profile, called by `make accept-pdf`). Every
subsequent run reads the profile — no PDF re-parse, no vision call.

Rules (decided, deliberate):
  - A new PDF ALWAYS regenerates the profile. No merge.
  - Hand-edits to profile.json are allowed and WILL be wiped on the next
    regeneration. The JSON is a correctable cache, not a hand-maintained
    config.
  - The profile is what runs use. The PDF is what regenerates it. They are
    never both authoritative — one derives from the other.

Shape:
  {
    "meta": {
      "generated_from": "portfolio.pdf",
      "generated_at": "2026-06-18T19:00:00Z",
      "display_currency": "CHF",
      "sandbox_accounts": ["Trading 212"]
    },
    "positions": [
      {"ticker","name","shares","account","currency",
       "classification","thesis","symbol_override","pdf_value_native"}
    ],
    "wealth": [
      {"label","value_native","currency","account"}
    ]
  }
"""

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path

import config


# ─── Models ──────────────────────────────────────────────────────────

@dataclass
class ProfilePosition:
    ticker: str
    name: str
    shares: float
    account: str = ""
    currency: str = ""              # currency of pdf_value_native
    classification: str = "conviction"   # "index" | "conviction" | "sandbox"
    thesis: str = ""
    symbol_override: str = ""       # yfinance symbol if the bare ticker won't resolve
    pdf_value_native: float = None  # fallback value if live pricing fails
    pdf_gain_pct: float = None      # % gain/loss shown in the PDF; with the
                                    # value it implies a cost basis, so live
                                    # value can be re-expressed as a running gain


@dataclass
class ProfileWealth:
    label: str
    value_native: float
    currency: str = ""
    account: str = ""


@dataclass
class Profile:
    display_currency: str
    sandbox_accounts: list
    positions: list             # list[ProfilePosition]
    wealth: list                # list[ProfileWealth]
    generated_from: str = ""
    generated_at: str = ""

    # ── convenience views ──
    def conviction(self) -> list:
        return [p for p in self.positions if p.classification == "conviction"]

    def index(self) -> list:
        return [p for p in self.positions if p.classification == "index"]

    def sandbox(self) -> list:
        return [p for p in self.positions if p.classification == "sandbox"]

    def tickers(self) -> list:
        return sorted({p.ticker for p in self.positions})

    def symbol_for(self, ticker: str) -> str:
        """Resolved price symbol: per-position override wins, else bare ticker."""
        for p in self.positions:
            if p.ticker == ticker and p.symbol_override:
                return p.symbol_override
        return ticker

    def age_days(self):
        """Days since the profile was generated from the PDF, or None if the
        timestamp is missing/unparseable. Drives staleness handling — an old
        PDF can't be trusted as the divergence guard's ground-truth oracle."""
        if not self.generated_at:
            return None
        try:
            gen = datetime.strptime(
                self.generated_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            return None
        return (datetime.now(timezone.utc) - gen).total_seconds() / 86400


# ─── Persistence ─────────────────────────────────────────────────────

def save(profile: Profile, path: Path = None) -> Path:
    path = path or config.PROFILE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "meta": {
            "generated_from": profile.generated_from,
            "generated_at": profile.generated_at,
            "display_currency": profile.display_currency,
            "sandbox_accounts": profile.sandbox_accounts,
        },
        "positions": [asdict(p) for p in profile.positions],
        "wealth": [asdict(w) for w in profile.wealth],
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def load(path: Path = None) -> Profile:
    """Load the profile. Raises FileNotFoundError if it doesn't exist —
    the caller (pipeline) turns that into a clear 'run accept-pdf first'."""
    path = path or config.PROFILE_PATH
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    meta = data.get("meta", {})
    positions = [ProfilePosition(**p) for p in data.get("positions", [])]
    wealth = [ProfileWealth(**w) for w in data.get("wealth", [])]
    return Profile(
        display_currency=meta.get("display_currency", "USD"),
        sandbox_accounts=meta.get("sandbox_accounts", []),
        positions=positions,
        wealth=wealth,
        generated_from=meta.get("generated_from", ""),
        generated_at=meta.get("generated_at", ""),
    )


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
