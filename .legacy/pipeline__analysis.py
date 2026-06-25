"""Analysis: call Claude to produce portfolio HTML from a screenshot.

This module owns all Claude API interactions for portfolio building.
The pipeline orchestrator calls into it; nothing else does.

Slice 2 scope: one function, build_portfolio_html. Takes a screenshot
envelope, returns an HTML string matching the structure of the example
template. Future slices will add reply-correction and digest modes.
"""

import base64
from pathlib import Path

from dotenv import load_dotenv
from anthropic import Anthropic

from inbox.envelope import Envelope


# Load Anthropic API key from .secrets/.env at import time.
# The Anthropic client picks up ANTHROPIC_API_KEY automatically.
load_dotenv(".secrets/.env")
_client = Anthropic()

MODEL = "claude-sonnet-4-6"

# Reference example: a fully-rendered HTML portfolio. Claude reads this
# to learn the structure (classes, layout, sections) it should produce.
# The file is generated once from pipeline/templates/portfolio.html +
# example_data.json — see README for the regeneration command.
_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
_EXAMPLE_RENDERED_PATH = _TEMPLATES_DIR / "example_rendered.html"


def _read_text(path: Path) -> str:
    """Read a text file. Returns empty string if missing — non-fatal."""
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _build_prompt(body_text: str) -> str:
    """Construct the user prompt for Claude.

    Includes the rendered example as a structural reference, plus any
    note the user wrote alongside the screenshot.
    """
    example = _read_text(_EXAMPLE_RENDERED_PATH)

    note_section = (
        f"The user wrote the following note alongside the screenshot:\n\n"
        f"{body_text}\n\n"
        if body_text.strip()
        else ""
    )

    return f"""You are producing a portfolio summary HTML document.

Below is an example of the EXACT HTML structure to produce. Match this
structure precisely — same elements, classes, and overall layout. Only
the content (numbers, positions, account names) changes per portfolio.

<example>
{example}
</example>

The user may have attached multiple screenshots showing different accounts. 
Aggregate them into a single portfolio document covering all accounts shown.

{note_section}

Rules:
- Produce a complete HTML document including the <style> block.
- Match the example's structure exactly.
- Numbers come from the screenshot, not the example.
- If a value is unclear, do your best — the user can correct it later.
- Output ONLY the HTML. No prose before or after, no markdown fences.
"""


def _strip_fences(text: str) -> str:
    """Strip ```html ... ``` fences if Claude added them despite instructions."""
    if not text.startswith("```"):
        return text
    # Drop the opening fence line (e.g. "```html\n" or "```\n")
    text = text.split("```", 2)[1]
    if text.startswith("html"):
        text = text[4:]
    text = text.strip()
    # Drop the trailing fence
    if text.endswith("```"):
        text = text[:-3].strip()
    return text



def build_portfolio_html(envelope: Envelope) -> str:
    """Send a screenshot envelope to Claude, return generated HTML.

    Reads the first image (or PDF) attachment, sends it to Claude with
    the build prompt, returns Claude's HTML response.

    Raises ValueError if the envelope has no visual attachment.
    """
    visual_attachments = [
        a for a in envelope.attachments
        if a.mime_type.startswith("image/") or a.mime_type == "application/pdf"
    ]
    if not visual_attachments:
        raise ValueError(f"envelope {envelope.id} has no visual attachment")

    # Build a content block with ALL images followed by the prompt
    content = []
    for attachment in visual_attachments:
        image_bytes = Path(attachment.path).read_bytes()
        image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": attachment.mime_type,
                "data": image_b64,
            },
        })

    content.append({
        "type": "text",
        "text": _build_prompt(envelope.body_text),
    })

    response = _client.messages.create(
        model=MODEL,
        max_tokens=8000,
        messages=[{"role": "user", "content": content}],
    )

    html = response.content[0].text.strip()
    return _strip_fences(html)