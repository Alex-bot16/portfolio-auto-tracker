"""Classify a parsed email by shape (screenshot / reply / unknown).

SCREENSHOT - does an email (with or without text) have at least 1 attatchment.
REPLY      - an email that replies to you.
UNKNOWN    - anything else.

This just classifies shape, understanding content will be done in `pipeline/`.
"""

from .gmail_parser import ParsedMessage
from inbox.envelope import EnvelopeKind

def classify(parsed: ParsedMessage) -> EnvelopeKind:
    """Return the EnvelopeKind for a parsed email.

    Rules, in priority order:
      1. At least one image-or-PDF attachment  → SCREENSHOT
      2. Has an In-Reply-To header              → REPLY
      3. Anything else                          → UNKNOWN
    """
    has_visual_attachment = any(
        a.mime_type.startswith("image/") or a.mime_type == "application/pdf"
        for a in parsed.attachments
    )
    if has_visual_attachment:
        return EnvelopeKind.SCREENSHOT

    if parsed.in_reply_to:
        return EnvelopeKind.REPLY

    return EnvelopeKind.UNKNOWN