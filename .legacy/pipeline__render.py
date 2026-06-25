"""Render: turn Claude's HTML output into a PDF on disk.

The pipeline produces HTML strings (via Claude). This module is the
last step that converts that HTML to a PDF file. WeasyPrint handles
the conversion; this module is just a thin wrapper that sets up paths
correctly.

The HTML must be self-contained (CSS inline, no external resources).
Future versions might support external CSS or images; for now,
self-contained keeps things simple.
"""

import os
from pathlib import Path

from weasyprint import HTML

# Returns sort of: /Users/.../pipeline/templates
_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


def render_to_pdf(html: str, output_path: str) -> None:
    """Render an HTML string to a PDF file at the given path.

    Creates the parent directory if it doesn't exist. Overwrites
    the output file if it already exists.

    The HTML is expected to be self-contained — any CSS inline,
    no external resources. WeasyPrint loads Google Fonts at render
    time if the HTML imports them via @import; that's fine.
    """
    parent = os.path.dirname(output_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    HTML(string=html, base_url=str(_TEMPLATES_DIR)).write_pdf(output_path)