"""Storage — where each run's two artifacts land on disk.

Per run, one timestamped folder under state/outputs/history/ holding:
  - portfolio_updated.pdf   the refreshed-values portfolio (email attachment)
  - portfolio_updated.md    its markdown source (handy for inspection)
  - research.md             the per-ticker + macro research (email body)

Append-only: nothing overwrites a past run. The newest folder is the
latest run. The portfolio PDF you supply remains the source of truth in
state/current/ — these are outputs, not state.
"""

from datetime import datetime, timezone
from pathlib import Path

import config
from io_layer.render import render_markdown_to_pdf


def save_run(valuations_md: str, research_md: str,
             render_pdf: bool = True) -> Path:
    """Write a run's artifacts to a fresh timestamped folder. Returns it.

    render_pdf=False skips PDF rendering (for tests / environments without
    WeasyPrint native deps) — only the markdown is written.
    """
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    folder = config.OUTPUTS_HISTORY_DIR / f"{stamp}_run"
    folder.mkdir(parents=True, exist_ok=True)

    (folder / "portfolio_updated.md").write_text(valuations_md, encoding="utf-8")
    (folder / "research.md").write_text(research_md, encoding="utf-8")

    if render_pdf:
        render_markdown_to_pdf(valuations_md, folder / "portfolio_updated.pdf")

    return folder
