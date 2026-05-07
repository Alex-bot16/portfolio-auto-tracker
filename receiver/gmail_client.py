"""
Simplifies complex Gmail API instructions to extract labels, messages, etc.
"""

import base64
from typing import Any

def get_label_id(service: Any, label_name: str) -> str:
    """Translate a human-readable label name to Gmail's internal ID.

    Gmail's API uses opaque internal IDs (e.g. "Label_3947") for labels.
    The human name (e.g. "portfolio/queued") is what users see, but the
    API needs the ID for searches and modifications. This function
    bridges the two.

    Raises:
        ValueError: if the label doesn't exist in the account.
    """
    result = service.users().labels().list(userId="me").execute()
    for label in result.get("labels", []):
        if label["name"] == label_name:
            return label["id"]
    raise ValueError(f"label not found: {label_name}")


def search_queued_messages(service: Any, label_name: str) -> list[str]:
    """Return message IDs of every message currently labeled with `label_name`.

    Returns an empty list if nothing matches.
    """
    result = service.users().messages().list(
        userId="me",
        q=f"label:{label_name}",
    ).execute()
    return [msg["id"] for msg in result.get("messages", [])]

def fetch_message(service: Any, message_id: str) -> dict:
    """Fetch one full message from Gmail.

    Returns the raw response dict from the API. The structure is deeply
    nested (headers, MIME parts, body data, attachment references) —
    parsing happens in `gmail_parser.py`, not here.

    Uses format="full", which returns headers + body + attachment
    *metadata*, but not the actual attachment bytes. Attachment bytes
    are fetched separately by `get_attachment_bytes`.
    """
    return service.users().messages().get(
        userId="me",
        id=message_id,
        format="full",
    ).execute()

def get_attachment_bytes(
    service: Any,
    message_id: str,
    attachment_id: str,
) -> bytes:
    """Download the raw bytes of one attachment.

    Both the message ID and the attachment ID are required — the
    attachment ID alone is meaningless without the message it belongs to.

    Gmail returns attachment data as a base64 string using the URL-SAFE
    variant (`-` and `_` instead of `+` and `/`). We decode with
    `urlsafe_b64decode` accordingly.
    """
    result = service.users().messages().attachments().get(
        userId="me",
        messageId=message_id,
        id=attachment_id,
    ).execute()
    return base64.urlsafe_b64decode(result["data"])


def relabel_message(
    service: Any,
    message_id: str,
    remove_label_id: str,
    add_label_id: str,
) -> None:
    """Atomically remove one label from a message and add another.

    Combining the operations into a single API call means we can never
    end up in a half-applied state — the message is never briefly tagged
    with both old and new labels, or with neither.

    Both label IDs are wrapped in lists because Gmail's modify endpoint
    accepts multiple labels per call (we just happen to use one each).

    Returns nothing. Used for its side effect on Gmail.
    """
    service.users().messages().modify(
        userId="me",
        id=message_id,
        body={
            "addLabelIds": [add_label_id],
            "removeLabelIds": [remove_label_id],
        },
    ).execute()