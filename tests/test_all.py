"""
End-to-end test suite for the portfolio-tracker.

Run from the project root:    python -m tests.test_all

This script verifies everything from the foundation up to the full
receiver, in three tiers:

    1. UNIT TESTS         — pure logic, no network, no auth
    2. INTEGRATION TESTS  — touches Gmail, requires auth
    3. END-TO-END TEST    — runs the full receiver, checks outputs

Each tier prints PASS or FAIL for individual checks. At the end, the
script exits 0 if everything passed, 1 otherwise.

Before running, make sure:
    - You're in the project root and venv is active
    - .secrets/credentials.json exists
    - .secrets/token.json exists (run python tests/test_auth.py once first)
    - At least one test email is queued in Gmail (or skip the
      end-to-end tier — it'll detect the empty queue)
"""

import base64
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


# ─────────────────────────────────────────────────────────────────────
# Test runner — tracks pass/fail counts so we can exit nonzero on fail
# ─────────────────────────────────────────────────────────────────────

class Runner:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.skipped = 0

    def section(self, name):
        print(f"\n{'═' * 70}")
        print(f"  {name}")
        print(f"{'═' * 70}")

    def check(self, label, condition, details=""):
        if condition:
            print(f"  ✓ {label}")
            self.passed += 1
        else:
            print(f"  ✗ {label}")
            if details:
                print(f"    {details}")
            self.failed += 1

    def skip(self, label, reason):
        print(f"  ⊘ {label} — skipped ({reason})")
        self.skipped += 1

    def summary(self):
        print(f"\n{'═' * 70}")
        total = self.passed + self.failed
        print(f"  RESULTS: {self.passed}/{total} passed, "
              f"{self.failed} failed, {self.skipped} skipped")
        print(f"{'═' * 70}\n")
        return 0 if self.failed == 0 else 1


r = Runner()


def b64(s: str) -> str:
    """url-safe base64-encode a string for fake Gmail payloads."""
    return base64.urlsafe_b64encode(s.encode("utf-8")).decode("ascii")


# ─────────────────────────────────────────────────────────────────────
# TIER 1: Unit tests
# ─────────────────────────────────────────────────────────────────────

r.section("TIER 1 — UNIT TESTS  (no network, no auth)")

# ---- Imports ----
try:
    from auth import (
        FileCredentialsProvider,
        GoogleOAuthFlow,
        GmailServiceFactory,
        get_service,
    )
    from auth.config import CLIENT_SECRETS_PATH, TOKEN_PATH, SCOPES
    from inbox.envelope import (
        Envelope,
        EnvelopeKind,
        Attachment,
        make_envelope_id,
    )
    from inbox.config import (
        PENDING_DIR,
    )
    from receiver.gmail_parser import (
        ParsedMessage,
        ParsedAttachment,
        parse_message,
        _walk_parts,
        _strip_html,
    )
    from receiver.classifier import classify
    from receiver.config import (
        QUEUED_LABEL,
        DONE_LABEL,
        FAILED_LABEL,
    )
    r.check("all package imports resolve", True)
except ImportError as e:
    r.check("all package imports resolve", False, f"ImportError: {e}")
    print("\nCannot continue without imports. Aborting.")
    sys.exit(r.summary())


# ---- Config sanity ----
r.check(
    "QUEUED_LABEL is set",
    isinstance(QUEUED_LABEL, str) and bool(QUEUED_LABEL),
)
r.check(
    "PENDING_DIR is a string path",
    isinstance(PENDING_DIR, str) and bool(PENDING_DIR),
)
r.check(
    "SCOPES has 3 entries",
    isinstance(SCOPES, list) and len(SCOPES) == 3,
)
r.check(
    "SCOPES includes readonly + modify + send",
    all(s in " ".join(SCOPES) for s in ["readonly", "modify", "send"]),
)


# ---- _walk_parts ----
single_part = {"mimeType": "text/plain", "body": {"data": b64("hi")}}
leaves = _walk_parts(single_part)
r.check(
    "_walk_parts handles single-part (no nesting)",
    len(leaves) == 1 and leaves[0] is single_part,
)

deep = {
    "mimeType": "multipart/mixed",
    "parts": [
        {
            "mimeType": "multipart/alternative",
            "parts": [
                {"mimeType": "text/plain", "body": {"data": b64("plain")}},
                {"mimeType": "text/html", "body": {"data": b64("<p>html</p>")}},
            ],
        },
        {
            "mimeType": "image/jpeg",
            "filename": "x.jpg",
            "body": {"attachmentId": "att1", "size": 100},
        },
    ],
}
leaves = _walk_parts(deep)
r.check(
    "_walk_parts flattens 2-level tree to 3 leaves",
    len(leaves) == 3,
    f"got {len(leaves)} leaves",
)


# ---- _strip_html ----
r.check("_strip_html keeps text content",
        _strip_html("<p>Hello</p>") == "Hello")
r.check("_strip_html removes tags",
        _strip_html("<b>bold</b> normal") == "bold normal")
r.check("_strip_html drops URLs",
        _strip_html("<a href='x'>click</a>") == "click")
r.check("_strip_html decodes HTML entities",
        _strip_html("M&amp;A") == "M&A")


# ---- parse_message ----
fake_msg = {
    "id": "msg_001",
    "threadId": "thread_001",
    "internalDate": "1714142400000",  # 2024-04-26 14:00 UTC
    "payload": {
        "mimeType": "multipart/mixed",
        "headers": [
            {"name": "From", "value": "alex@gmail.com"},
            {"name": "Subject", "value": "test"},
        ],
        "parts": [
            {"mimeType": "text/plain", "body": {"data": b64("body text")}},
            {
                "mimeType": "image/jpeg",
                "filename": "screenshot.jpeg",
                "body": {"attachmentId": "ATT_X", "size": 5000},
            },
        ],
    },
}
parsed = parse_message(fake_msg)
r.check("parse_message extracts ID",
        parsed.gmail_message_id == "msg_001")
r.check("parse_message extracts From",
        parsed.from_address == "alex@gmail.com")
r.check("parse_message extracts Subject",
        parsed.subject == "test")
r.check("parse_message extracts body_text",
        parsed.body_text == "body text")
r.check("parse_message extracts 1 attachment",
        len(parsed.attachments) == 1)
r.check("parse_message attachment has filename",
        parsed.attachments[0].filename == "screenshot.jpeg")


# ---- Header case-insensitivity ----
fake_msg_uppercase = {
    "id": "msg_002",
    "threadId": "thread_002",
    "internalDate": "1714142400000",
    "payload": {
        "headers": [{"name": "FROM", "value": "x@y.com"}],
        "body": {"data": b64("hi")},
    },
}
parsed2 = parse_message(fake_msg_uppercase)
r.check("parse_message handles uppercase header names",
        parsed2.from_address == "x@y.com")


# ---- Inline images skipped ----
fake_msg_inline = {
    "id": "msg_003",
    "threadId": "thread_003",
    "internalDate": "1714142400000",
    "payload": {
        "headers": [{"name": "From", "value": "x@y.com"}],
        "parts": [
            {"mimeType": "text/plain", "body": {"data": b64("hi")}},
            {
                "mimeType": "image/png",
                "filename": "",  # inline image — no filename
                "body": {"attachmentId": "INLINE_X", "size": 100},
            },
        ],
    },
}
parsed3 = parse_message(fake_msg_inline)
r.check("parse_message skips inline images (no filename)",
        len(parsed3.attachments) == 0)


# ---- classify ----
def make_msg(attachments=None, in_reply_to=None):
    return ParsedMessage(
        gmail_message_id="x", gmail_thread_id="x",
        from_address="alex@gmail.com", subject="t",
        internal_date=datetime.now(timezone.utc),
        in_reply_to=in_reply_to,
        body_text="",
        attachments=attachments or [],
    )

def make_att(mime="image/jpeg"):
    return ParsedAttachment("x.jpg", mime, 100, "id1")


r.check("classify: image → SCREENSHOT",
        classify(make_msg(attachments=[make_att()])) == EnvelopeKind.SCREENSHOT)
r.check("classify: pdf → SCREENSHOT",
        classify(make_msg(attachments=[make_att("application/pdf")])) == EnvelopeKind.SCREENSHOT)
r.check("classify: text-only attachment → UNKNOWN",
        classify(make_msg(attachments=[make_att("text/plain")])) == EnvelopeKind.UNKNOWN)
r.check("classify: reply with no attachment → REPLY",
        classify(make_msg(in_reply_to="<msg@gmail.com>")) == EnvelopeKind.REPLY)
r.check("classify: empty → UNKNOWN",
        classify(make_msg()) == EnvelopeKind.UNKNOWN)
r.check("classify: image+reply → SCREENSHOT (priority)",
        classify(make_msg(attachments=[make_att()], in_reply_to="<x>")) == EnvelopeKind.SCREENSHOT)


# ---- Envelope round-trip ----
env = Envelope(
    schema_version=1,
    id=make_envelope_id(datetime.now(timezone.utc)),
    received_at=datetime.now(timezone.utc),
    kind=EnvelopeKind.SCREENSHOT,
    source="gmail",
    source_metadata={"gmail_message_id": "abc"},
    body_text="hello",
    attachments=[
        Attachment("x.jpg", "inbox/pending/abc/x.jpg", "image/jpeg", 1234),
    ],
)
raw = env.to_json()
env2 = Envelope.from_json(raw)
r.check("Envelope serializes to JSON",
        isinstance(raw, str) and len(raw) > 0)
r.check("Envelope round-trips: kind preserved",
        env2.kind == EnvelopeKind.SCREENSHOT)
r.check("Envelope round-trips: kind is enum, not string",
        isinstance(env2.kind, EnvelopeKind))
r.check("Envelope round-trips: received_at is datetime",
        isinstance(env2.received_at, datetime))
r.check("Envelope round-trips: attachments preserved",
        len(env2.attachments) == 1 and env2.attachments[0].filename == "x.jpg")
r.check("Envelope round-trips: produces identical JSON",
        env2.to_json() == raw)


# ---- Envelope.write_to is atomic ----
with tempfile.TemporaryDirectory() as tmp:
    target = os.path.join(tmp, "sub", "envelope.json")
    env.write_to(target)
    r.check("Envelope.write_to creates parent directory",
            os.path.exists(target))
    r.check("Envelope.write_to does NOT leave a .tmp file",
            not os.path.exists(target + ".tmp"))
    with open(target) as f:
        loaded = Envelope.from_json(f.read())
    r.check("Envelope.write_to output is loadable",
            loaded.id == env.id)


# ---- make_envelope_id ----
id1 = make_envelope_id(datetime(2026, 5, 7, 14, 22, 8, tzinfo=timezone.utc))
id2 = make_envelope_id(datetime(2026, 5, 7, 14, 22, 8, tzinfo=timezone.utc))
r.check("make_envelope_id is sortable (timestamp prefix)",
        id1.startswith("2026-05-07T14-22-08__"))
r.check("make_envelope_id has random suffix (no collisions)",
        id1 != id2)
r.check("make_envelope_id uses dashes, not colons (filesystem-safe)",
        ":" not in id1)


# ─────────────────────────────────────────────────────────────────────
# TIER 2: Integration tests (require auth + network)
# ─────────────────────────────────────────────────────────────────────

r.section("TIER 2 — INTEGRATION TESTS  (requires auth + network)")

if not Path(".secrets/credentials.json").exists():
    r.skip("integration tests", "no .secrets/credentials.json")
    service = None
elif not Path(".secrets/token.json").exists():
    r.skip("integration tests", "no .secrets/token.json — run tests/test_auth.py first")
    service = None
else:
    try:
        provider = FileCredentialsProvider(CLIENT_SECRETS_PATH, TOKEN_PATH)
        flow = GoogleOAuthFlow(provider, SCOPES)
        factory = GmailServiceFactory()
        service = get_service(flow, factory)
        r.check("auth: get_service returns a service object", service is not None)
    except Exception as e:
        r.check("auth: get_service returns a service object",
                False, f"failed: {e}")
        service = None


ids = []  # default; populated below if integration runs

if service:
    from receiver.gmail_client import (
        get_label_id,
        search_queued_messages,
        fetch_message,
        get_attachment_bytes,
    )

    # ---- get_label_id ----
    try:
        queued_id = get_label_id(service, QUEUED_LABEL)
        r.check(f"gmail_client: queued label resolves",
                isinstance(queued_id, str) and bool(queued_id))
    except Exception as e:
        r.check("gmail_client: queued label resolves",
                False, f"failed: {e}")
        queued_id = None

    try:
        get_label_id(service, "this-label-does-not-exist-xyz")
        r.check("gmail_client: missing label raises ValueError",
                False, "didn't raise")
    except ValueError:
        r.check("gmail_client: missing label raises ValueError", True)
    except Exception as e:
        r.check("gmail_client: missing label raises ValueError",
                False, f"raised wrong type: {type(e).__name__}")

    # ---- search_queued_messages ----
    try:
        ids = search_queued_messages(service, QUEUED_LABEL)
        r.check("gmail_client: search returns a list",
                isinstance(ids, list))
        print(f"    queue currently holds {len(ids)} message(s)")
    except Exception as e:
        r.check("gmail_client: search returns a list",
                False, f"failed: {e}")
        ids = []

    # ---- fetch + parse + classify on a real message ----
    if ids:
        msg_id = ids[0]
        try:
            raw = fetch_message(service, msg_id)
            r.check("gmail_client: fetch_message returns dict",
                    isinstance(raw, dict) and "id" in raw)
        except Exception as e:
            r.check("gmail_client: fetch_message returns dict",
                    False, f"failed: {e}")
            raw = None

        if raw:
            parsed = parse_message(raw)
            r.check("real message: parser produces ParsedMessage",
                    isinstance(parsed, ParsedMessage))
            r.check("real message: from_address present",
                    bool(parsed.from_address))

            kind = classify(parsed)
            r.check(f"real message: classifier returns {kind.value}",
                    isinstance(kind, EnvelopeKind))

            print(f"    real message details:")
            print(f"      from:       {parsed.from_address}")
            print(f"      subject:    {parsed.subject}")
            print(f"      kind:       {kind.value}")
            print(f"      attachments: {len(parsed.attachments)}")
            print(f"      body_text:  {parsed.body_text[:60]!r}"
                  + ("..." if len(parsed.body_text) > 60 else ""))
    else:
        r.skip("real-message tests", "queue is empty")


# ─────────────────────────────────────────────────────────────────────
# TIER 3: End-to-end (full receiver run + outputs check)
# ─────────────────────────────────────────────────────────────────────

r.section("TIER 3 — END-TO-END  (full receiver run)")

if not service:
    r.skip("end-to-end test", "no auth available")
elif not ids:
    r.skip("end-to-end test", "queue is empty (forward an email and re-run)")
else:
    # Snapshot directory before
    pending_before = set(os.listdir(PENDING_DIR)) if os.path.exists(PENDING_DIR) else set()
    queue_before = len(ids)

    try:
        from receiver.gmail_receiver import run as run_receiver
        print(f"    running receiver against {queue_before} queued message(s)...")
        run_receiver()
        r.check("end-to-end: receiver completed without exception", True)
    except Exception as e:
        r.check("end-to-end: receiver completed without exception",
                False, f"crashed: {e}")
        print(f"\n  full traceback follows:")
        import traceback
        traceback.print_exc()
        sys.exit(r.summary())

    # Snapshot after
    pending_after = set(os.listdir(PENDING_DIR)) if os.path.exists(PENDING_DIR) else set()
    new_envelope_folders = pending_after - pending_before

    r.check(f"end-to-end: new envelope folder(s) written ({len(new_envelope_folders)} new)",
            len(new_envelope_folders) >= 1)

    # Verify the envelope folder is well-formed
    if new_envelope_folders:
        first = sorted(new_envelope_folders)[0]
        folder = os.path.join(PENDING_DIR, first)

        r.check(f"end-to-end: new entry is a directory",
                os.path.isdir(folder),
                f"path: {folder}")

        envelope_json = os.path.join(folder, "envelope.json")
        r.check(f"end-to-end: envelope.json exists in folder",
                os.path.exists(envelope_json))

        try:
            with open(envelope_json) as f:
                env = Envelope.from_json(f.read())
            r.check("end-to-end: envelope.json is loadable",
                    isinstance(env, Envelope))
            r.check("end-to-end: envelope has valid kind",
                    isinstance(env.kind, EnvelopeKind))

            # If it's a screenshot, attachment files should exist in the folder
            if env.kind == EnvelopeKind.SCREENSHOT and env.attachments:
                attachment_path = env.attachments[0].path
                r.check(f"end-to-end: attachment file exists at {attachment_path}",
                        os.path.exists(attachment_path))

                size_on_disk = os.path.getsize(attachment_path)
                r.check(f"end-to-end: attachment size matches envelope ({size_on_disk} bytes)",
                        size_on_disk == env.attachments[0].size_bytes)
        except Exception as e:
            r.check("end-to-end: envelope.json is loadable",
                    False, f"failed: {e}")

    # Verify the queue drained
    ids_after = search_queued_messages(service, QUEUED_LABEL)
    r.check(f"end-to-end: queue drained "
            f"({queue_before} → {len(ids_after)} messages)",
            len(ids_after) < queue_before)


# ─────────────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────────────

sys.exit(r.summary())