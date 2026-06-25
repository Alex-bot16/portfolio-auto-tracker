"""Parse a raw Gmail API message into clean Python data.

Gmail returns messages as deeply nested dicts:

    Gmail message (top-level dict)
    ├── id, threadId, labelIds, snippet, internalDate    ← metadata
    └── payload                                          ← content
        ├── headers (list of {name, value})              ← From, Subject, etc.
        └── parts (recursive tree)
            ├── leaf with body.data                      → body text/html
            └── leaf with body.attachmentId + filename   → attachment reference

This module flattens that into ParsedMessage and ParsedAttachment dataclasses
that downstream code (classifier, envelope-builder) can read without knowing
anything about Gmail's structure.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser 
import base64

@dataclass
class ParsedAttachment:
    filename: str
    mime_type: str
    size_bytes: int
    attachment_id: str   # opaque Gmail reference, used to fetch bytes

@dataclass
class ParsedMessage:
    gmail_message_id: str
    gmail_thread_id: str
    from_address: str
    subject: str
    internal_date: datetime
    in_reply_to: str | None
    body_text: str
    attachments: list[ParsedAttachment]

def parse_message(raw: dict) -> ParsedMessage:
    """Parse a raw Gmail API response into a clean ParsedMessage."""
    payload = raw.get("payload", {})
    headers = payload.get("headers", [])

    return ParsedMessage(
        gmail_message_id=raw["id"],
        gmail_thread_id=raw["threadId"],
        from_address=_get_header(headers, "From") or "",
        subject=_get_header(headers, "Subject") or "",
        internal_date=_parse_internal_date(raw["internalDate"]),
        in_reply_to=_get_header(headers, "In-Reply-To"),
        body_text=_extract_body_text(payload),
        attachments=_extract_attachments(payload),
    )

def _get_header(headers: list[dict], name: str) -> str | None:
    """Find a header's value by name. Case-insensitive."""
    for h in headers:
        if h["name"].lower() == name.lower():
            return h["value"]
    return None

def _parse_internal_date(raw: str) -> datetime:
    """Convert Gmail's internalDate (ms since epoch as string) to a datetime object."""
    return datetime.fromtimestamp(int(raw) / 1000, tz=timezone.utc)

def _walk_parts(payload: dict) -> list[dict]:
    """Recursively collect every leaf part in a MIME (Multipurpose Internet Mail Extension) tree.

    A part is a leaf if it has no nested `parts` array. Single-part
    messages (no nesting) return a list containing just the payload itself.

    A leaf is like:
            {
            "mimeType": "text/plain",
            "body": {
                "data": "PGJhc2U2NC11cmwtc2FmZS1lbmNvZGVkPg==",   # the actual content
                "size": 42
            }
        }
    """

    # The leaf objects
    leaves = []

    # If something returns, it means there is still more nesting
    parts = payload.get("parts")

    if parts:
        for part in parts:
            # Add on all the leaves found in sub functions
            leaves.extend(_walk_parts(part))
    else:
        # Append the current payload that was found
        leaves.append(payload)
    return leaves

def _strip_html(html: str) -> str:
    """Convert HTML to plain text.

    Used only as a fallback when an email has no text/plain body (and only includes text/html). Most emails
    include both, in which case this function never runs.

    Examples:
        Input:  "<p>Hello</p>"
        Output: "Hello"

        Input:  "<b>WMT</b> closed today"
        Output: "WMT closed today"

        Input:  "<a href='https://x.com'>click here</a>"
        Output: "click here"          # the URL is lost

        Input:  "<p>line 1</p><p>line 2</p>"
        Output: "line 1line 2"        # no newline inserted between blocks

        Input:  "M&amp;A activity"
        Output: "M&A activity"    

    Limitations are deliberate — this is the fallback path, not the main one.
    Body text quality matters less than reliability. If quality ever becomes
    a problem, swap this for the `beautifulsoup4` library.
    """

    class _Stripper(HTMLParser):
        def __init__(self):
            super().__init__()
            self.parts = []

        def handle_data(self, data):
            self.parts.append(data)

    s = _Stripper()
    s.feed(html)
    return "".join(s.parts).strip()

def _extract_body_text(payload: dict) -> str:
    """Extract the body text from a message payload.

    Prefers text/plain. Falls back to text/html (with tags stripped) if
    no plain version exists. Returns empty string if there's no body at all.
    """
    plain_text = None
    html_text = None

    for part in _walk_parts(payload):
        mime = part.get("mimeType", "")
        body = part.get("body", {})
        data = body.get("data")

        # Skip parts without inline data.
        # Attachments have body.attachmentId instead of body.data.
        if not data:
            continue

        decoded = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")

        # Checks text/plain or text/html
        if mime == "text/plain" and plain_text is None:
            plain_text = decoded
        elif mime == "text/html" and html_text is None:
            html_text = decoded

    if plain_text is not None:
        return plain_text
    if html_text is not None:
        return _strip_html(html_text)
    return ""

def _extract_attachments(payload: dict) -> list[ParsedAttachment]:
    """Return a list of every attachment in the message.

    We dont take the attatchment bytes itself, we keep a reference
    with attachment_id which we can call later.
    """
    attachments = []

    for part in _walk_parts(payload):
        body = part.get("body", {})
        attachment_id = body.get("attachmentId")
        filename = part.get("filename", "")

        if not attachment_id or not filename:
            continue

        attachments.append(ParsedAttachment(
            filename=filename,
            mime_type=part.get("mimeType", "application/octet-stream"),
            size_bytes=body.get("size", 0),
            attachment_id=attachment_id,
        ))

    return attachments