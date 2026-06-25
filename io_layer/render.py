"""Render — turn the digest markdown into a PDF.

Minimal on purpose. Wraps the markdown in a small HTML shell with a bit
of CSS, then WeasyPrint renders it. If WeasyPrint isn't available (its
native deps not installed), render_markdown_to_pdf raises a clear error
so you know to `brew install pango`.

We don't need the elaborate portfolio template from the old system —
the digest is text-and-tables, so plain styled HTML is plenty.
"""

from pathlib import Path

_CSS = """
@page { size: A4; margin: 18mm 16mm; }
body {
  font-family: -apple-system, "Segoe UI", Helvetica, Arial, sans-serif;
  font-size: 10.5pt; line-height: 1.45; color: #1f2933;
}
h1 { font-size: 20pt; margin: 0 0 2px; }
h2 { font-size: 14pt; margin: 18px 0 6px; border-top: 1px solid #e6e8eb;
     padding-top: 10px; }
table { width: 100%; border-collapse: collapse; margin: 8px 0; font-size: 9.5pt; }
th, td { text-align: left; padding: 5px 7px; border-bottom: 1px solid #eef0f3; }
th { background: #f6f7f9; text-transform: uppercase; font-size: 7.5pt;
     letter-spacing: 0.06em; color: #6f7882; }
td:nth-child(n+3), th:nth-child(n+3) { text-align: right; }
em { color: #8b95a1; }
a { color: #1a66cc; text-decoration: none; }
hr { border: none; border-top: 1px solid #e6e8eb; margin: 16px 0; }
"""


def render_markdown_to_pdf(markdown_text: str, output_path: Path) -> Path:
    """Render markdown to a PDF at output_path. Returns the path."""
    try:
        import markdown as md
    except ImportError:
        raise ImportError("The 'markdown' package is required. "
                          "pip install markdown")
    try:
        from weasyprint import HTML
    except Exception as e:
        raise ImportError(
            "WeasyPrint is required and needs native libs. On macOS: "
            "`brew install pango`. Original error: " + str(e)
        )

    body_html = md.markdown(markdown_text, extensions=["tables"])
    full_html = (
        f"<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"<style>{_CSS}</style></head><body>{body_html}</body></html>"
    )

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=full_html).write_pdf(str(output_path))
    return output_path
