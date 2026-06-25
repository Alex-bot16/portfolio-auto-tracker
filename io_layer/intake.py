"""Intake — accept a portfolio PDF as the new source of truth.

You build a portfolio PDF in Claude.ai, download it, and drop it into
portfolio_inbox/. Running accept_latest_pdf() (via `make accept-pdf`)
takes the newest PDF there, makes it the canonical portfolio, versions
the previous one into history, and clears the inbox.

There's no server and nothing to restart. "Updating the portfolio" is
just: drop a file, run one command. The file on disk IS the state.
"""

import shutil
from datetime import datetime, timezone
from pathlib import Path

import config


def accept_latest_pdf() -> Path:
    """Promote the newest PDF in portfolio_inbox/ to the canonical slot.

    Steps:
      1. Find the most recently modified *.pdf in portfolio_inbox/.
      2. If a current portfolio exists, archive it to state/portfolios/
         with a timestamp (so you keep a version history).
      3. Copy the new PDF to state/current/portfolio.pdf.
      4. Remove the accepted file from portfolio_inbox/.

    Returns the path to the new canonical PDF.
    Raises FileNotFoundError if portfolio_inbox/ has no PDF.
    """
    config.INBOX_DIR.mkdir(parents=True, exist_ok=True)
    config.CURRENT_DIR.mkdir(parents=True, exist_ok=True)
    config.PORTFOLIOS_DIR.mkdir(parents=True, exist_ok=True)

    pdfs = sorted(
        config.INBOX_DIR.glob("*.pdf"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not pdfs:
        raise FileNotFoundError(
            f"No PDF found in {config.INBOX_DIR}. "
            f"Drop a portfolio PDF there first."
        )
    newest = pdfs[0]

    # Archive the existing current portfolio, if any.
    if config.CURRENT_PDF.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
        archived = config.PORTFOLIOS_DIR / f"{stamp}_portfolio.pdf"
        shutil.copy(config.CURRENT_PDF, archived)

    # Promote the new one.
    shutil.copy(newest, config.CURRENT_PDF)

    # Clear it from the inbox.
    newest.unlink()

    return config.CURRENT_PDF
