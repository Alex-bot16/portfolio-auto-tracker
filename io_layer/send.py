"""Send — deliver a run: research as the email BODY, the updated-values
PDF as the ATTACHMENT.

Behind a tiny interface so the backend swaps cleanly. The only backend now
is LocalStubSender, which prints what WOULD be sent (no email, no Gmail
auth needed). When you want real email, implement GmailSender with the same
send() signature and flip ACTIVE_SENDER at the bottom — nothing else changes.
"""

from abc import ABC, abstractmethod
from pathlib import Path


class Sender(ABC):
    @abstractmethod
    def send(self, subject: str, body_markdown: str,
             attachment_path: Path | None) -> None:
        ...


class LocalStubSender(Sender):
    """No-op delivery: report what would be sent. Lets the full pipeline
    run end-to-end with zero email setup."""

    def send(self, subject: str, body_markdown: str,
             attachment_path: Path | None) -> None:
        print("─" * 60)
        print("EMAIL READY (stub — nothing sent)")
        print(f"  subject:    {subject}")
        if attachment_path and Path(attachment_path).exists():
            print(f"  attachment: {attachment_path}")
        else:
            print(f"  attachment: (none / not rendered)")
        preview = body_markdown.strip().splitlines()
        head = preview[0] if preview else ""
        print(f"  body:       {len(body_markdown)} chars, starts: {head!r}")
        print("  To enable real email, implement GmailSender in send.py")
        print("  and set ACTIVE_SENDER = GmailSender().")
        print("─" * 60)


# When ready for real delivery:
#
# class GmailSender(Sender):
#     def send(self, subject, body_markdown, attachment_path):
#         # render body_markdown -> HTML, build a MIME message with the
#         # PDF attached, send via the Gmail API (lift auth/ from legacy/).
#         ...


# ─── The one line you flip to change delivery ────────────────────────
ACTIVE_SENDER: Sender = LocalStubSender()


def send(subject: str, body_markdown: str,
         attachment_path: Path | None = None) -> None:
    """Deliver via whichever backend ACTIVE_SENDER points at."""
    ACTIVE_SENDER.send(subject, body_markdown, attachment_path)
