"""Send — deliver a run: research as the email BODY, the updated-values
PDF as the ATTACHMENT.

Behind a tiny interface so the backend swaps cleanly:
  - LocalStubSender — prints what WOULD be sent (no email, no setup). Default.
  - GmailSender     — real delivery over SMTP using a Gmail App Password.

Recipients are resolved at send time (easy to change, never in tracked code):
  1. an explicit override  (e.g. `make send TO=a@x.com`)
  2. DIGEST_RECIPIENTS in .secrets/.env  (comma-separated; the usual knob)
  3. else SMTP_USER        (send to yourself)

Delivery secrets live in .secrets/.env (gitignored), NOT in code:
  SMTP_USER, SMTP_APP_PASSWORD, DIGEST_RECIPIENTS, and DIGEST_SENDER=gmail
  to flip the active backend to real send without editing this file.
"""

import os
import ssl
import smtplib
from abc import ABC, abstractmethod
from email.message import EmailMessage
from pathlib import Path

import markdown
from dotenv import load_dotenv

import config

load_dotenv(config.ENV_PATH)

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465


def resolve_recipients(override: str | list | None = None) -> list[str]:
    """Resolve the recipient list: explicit override, else DIGEST_RECIPIENTS,
    else SMTP_USER (yourself). Accepts a comma-separated string or a list."""
    raw = override if override else os.environ.get("DIGEST_RECIPIENTS", "")
    if not raw:
        me = os.environ.get("SMTP_USER", "").strip()
        return [me] if me else []
    parts = raw if isinstance(raw, list) else str(raw).split(",")
    return [e.strip() for e in parts if e.strip()]


class Sender(ABC):
    @abstractmethod
    def send(self, subject: str, body_markdown: str,
             attachment_path: Path | None, recipients: list[str]) -> None:
        ...


class LocalStubSender(Sender):
    """No-op delivery: report what would be sent. Lets the full pipeline
    run end-to-end with zero email setup."""

    def send(self, subject: str, body_markdown: str,
             attachment_path: Path | None, recipients: list[str]) -> None:
        print("─" * 60)
        print("EMAIL READY (stub — nothing sent)")
        print(f"  to:         {', '.join(recipients) if recipients else '(none set)'}")
        print(f"  subject:    {subject}")
        if attachment_path and Path(attachment_path).exists():
            print(f"  attachment: {attachment_path}")
        else:
            print("  attachment: (none / not rendered)")
        head = (body_markdown.strip().splitlines() or [""])[0]
        print(f"  body:       {len(body_markdown)} chars, starts: {head!r}")
        print("  To send for real: set SMTP_USER/SMTP_APP_PASSWORD/DIGEST_RECIPIENTS")
        print("  and DIGEST_SENDER=gmail in .secrets/.env.")
        print("─" * 60)


class GmailSender(Sender):
    """Real delivery over Gmail SMTP using an App Password (stdlib only).

    Requires SMTP_USER + SMTP_APP_PASSWORD in .secrets/.env. The App Password
    is a 16-char credential you generate once (Google account → 2-Step
    Verification → App passwords); it is NOT your Google login password.
    """

    def _build_message(self, subject: str, body_markdown: str,
                       attachment_path: Path | None, recipients: list[str],
                       sender: str) -> EmailMessage:
        """Build a multipart/alternative (text + HTML) message, with the PDF
        attached when present. Pure — no network — so it's unit-testable."""
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = sender
        msg["To"] = ", ".join(recipients)
        msg.set_content(body_markdown)                       # text/plain fallback
        msg.add_alternative(markdown.markdown(body_markdown), subtype="html")
        if attachment_path and Path(attachment_path).exists():
            data = Path(attachment_path).read_bytes()
            msg.add_attachment(data, maintype="application", subtype="pdf",
                               filename=Path(attachment_path).name)
        return msg

    def send(self, subject: str, body_markdown: str,
             attachment_path: Path | None, recipients: list[str]) -> None:
        user = os.environ.get("SMTP_USER", "").strip()
        # App Passwords are shown as "abcd efgh ijkl mnop"; strip ALL spaces so
        # a pasted-with-spaces value works (Gmail tolerates them, but be safe).
        password = "".join(os.environ.get("SMTP_APP_PASSWORD", "").split())
        if not recipients:
            raise ValueError("no recipients — set DIGEST_RECIPIENTS in .secrets/.env "
                             "or pass TO=...")
        if not user or not password:
            raise ValueError("Gmail send needs SMTP_USER and SMTP_APP_PASSWORD in "
                             ".secrets/.env (App Password, not your login password).")
        msg = self._build_message(subject, body_markdown, attachment_path,
                                  recipients, sender=user)
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT,
                              context=ssl.create_default_context()) as s:
            s.login(user, password)
            s.send_message(msg)
        print(f"sent → {', '.join(recipients)} (subject: {subject!r})")


# ─── Backend selection ───────────────────────────────────────────────
# Stub by default (safe — never sends by accident). Set DIGEST_SENDER=gmail
# in .secrets/.env to go live; no code edit needed.
ACTIVE_SENDER: Sender = (
    GmailSender() if os.environ.get("DIGEST_SENDER", "").lower() == "gmail"
    else LocalStubSender()
)


def send(subject: str, body_markdown: str,
         attachment_path: Path | None = None,
         to: str | list | None = None) -> None:
    """Deliver via ACTIVE_SENDER, resolving recipients (override -> env -> self)."""
    ACTIVE_SENDER.send(subject, body_markdown, attachment_path,
                       resolve_recipients(to))
