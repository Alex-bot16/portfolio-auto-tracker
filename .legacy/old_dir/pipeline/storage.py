"""Storage: where portfolios and digests live on disk.

Two destinations:
  - current/   — always the latest portfolio. Overwritten on each new
                  save. This is what the system reads when it needs to
                  know "what is the current state."
  - history/   — append-only chronological record. Each portfolio/digest gets
                  its own timestamped folder.

Portfolios are identified by the moment they're produced, not by which
envelope produced them. The history is a portfolio timeline, not an
envelope archive — those are kept separately in inbox/processed/.

By convention: write to history first (atomic single artifact), then
mirror to current/. That way current/ is never half-written.
"""

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from inbox.config import CURRENT_DIR, HISTORY_DIR
from pipeline.render import render_to_pdf


def _timestamp_for_folder() -> str:
    """A filesystem-safe timestamp prefix: YYYY-MM-DDTHH-MM-SS."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")


def save_portfolio(html: str, source_paths: list[str]) -> str:
    """Save a portfolio (HTML + PDF + source screenshots) to disk.

    Writes everything to history/<timestamp>_portfolio/, then mirrors
    that folder's contents into current/.

    Returns the absolute path to the new history folder.
    """
    timestamp = _timestamp_for_folder()
    history_folder = os.path.join(HISTORY_DIR, f"{timestamp}_portfolio")
    history_source = os.path.join(history_folder, "source")

    # 1. Create folders
    os.makedirs(history_source, exist_ok=True)

    # 2. Write HTML and render PDF
    html_path = os.path.join(history_folder, "portfolio.html")
    Path(html_path).write_text(html, encoding="utf-8")

    pdf_path = os.path.join(history_folder, "portfolio.pdf")
    render_to_pdf(html, pdf_path)

    # 3. Copy source screenshots into source/
    for src_path in source_paths:
        if not os.path.exists(src_path):
            continue  # source missing — skip rather than crash
        filename = os.path.basename(src_path)
        shutil.copy(src_path, os.path.join(history_source, filename))

    # 4. Mirror to current/ (wipe and replace)
    if os.path.exists(CURRENT_DIR):
        shutil.rmtree(CURRENT_DIR)
    shutil.copytree(history_folder, CURRENT_DIR)

    return os.path.abspath(history_folder)