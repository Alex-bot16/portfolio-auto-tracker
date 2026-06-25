"""
Gmail receiver — orchestrates one full pass over the queue.


WHAT THIS MODULE DOES
─────────────────────

This is the entry point for the receiver. When called (typically by
`python -m receiver`, eventually by GitHub Actions cron), it does
exactly one pass over the Gmail queue:

  1. Authenticate against Gmail (via the auth package)
  2. Find every message currently labeled "portfolio/queued"
  3. For each one, process it into an Envelope on disk
  4. Relabel processed messages from "queued" to "done"
  5. Print a summary of what happened
  6. Exit

It does not loop. It does not wait. It does not run as a server. Each
invocation is a single pass — the *schedule* is what makes it recur.
The receiver runs every ~15 minutes via cron (eventually); each run
drains whatever has accumulated since the last one.


PROCESSING ONE MESSAGE
──────────────────────

`_process_one()` does the per-message work, in this exact order:

  1. fetch_message()         — pull the full message from Gmail
  2. parse_message()         — flatten it into a clean ParsedMessage
  3. classify()              — decide its kind (screenshot/reply/unknown)
  4. make_envelope_id()      — generate a unique sortable ID
  5. for each attachment:
       a. download bytes from Gmail
       b. write atomically to inbox/blobs/<id>__<filename>
       c. record a saved-Attachment for the envelope
  6. build the Envelope object
  7. envelope.write_to(inbox/pending/<id>.json)   ← atomic
  8. relabel_message: queued → done               ← LAST step

Step 8 — the relabel — is intentionally the last thing. Everything
before it is recoverable: if we crash, the message stays queued and
gets retried next run. If we relabeled too early, a mid-write crash
would lose data forever. The rule is: never lose data, even if it
means occasional duplicates.


ERROR HANDLING
──────────────

`run()` wraps each call to `_process_one()` in try/except. If one
message fails, the others still process. Failed messages get the
"portfolio/failed" label so they don't get retried in a loop, and so
you can investigate them manually in Gmail.

If even the failure-relabeling fails (e.g., network drop), we log it
and move on. We never let one bad message kill the whole run.


WHAT THIS MODULE DOES NOT DO
────────────────────────────

  - Read attachment contents.            That's the pipeline's job.
  - Call Claude.                         That's the pipeline's job.
  - Generate digests, send emails.       That's the pipeline's job.
  - Decide what an email "means."        Classifier looks at shape only.

The receiver is a transport layer. It moves data from Gmail to disk
and labels things. Analysis is downstream and decoupled — the two
halves never run in the same process.
"""

from datetime import datetime, timezone

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

from inbox.config import PENDING_DIR

from .config import (
    QUEUED_LABEL,
    DONE_LABEL,
    FAILED_LABEL,
    
)
from .gmail_client import (
    get_label_id,
    search_queued_messages,
    fetch_message,
    get_attachment_bytes,
    relabel_message,
)
from .gmail_parser import parse_message
from .classifier import classify
import os

def run() -> None:
    """Entry point. Process all messages currently in the queued label."""
    # 1. Build authenticated Gmail service
    provider = FileCredentialsProvider(CLIENT_SECRETS_PATH, TOKEN_PATH)
    flow = GoogleOAuthFlow(provider, SCOPES)
    factory = GmailServiceFactory()
    service = get_service(flow, factory)

    # 2. Resolve label names to IDs (used for modify operations)
    queued_id = get_label_id(service, QUEUED_LABEL)
    done_id = get_label_id(service, DONE_LABEL)
    failed_id = get_label_id(service, FAILED_LABEL)

    # 3. Search the queue
    message_ids = search_queued_messages(service, QUEUED_LABEL)
    print(f"found {len(message_ids)} queued messages")

    # 4. Process each message individually
    succeeded, failed = 0, 0
    for msg_id in message_ids:
        try:
            _process_one(service, msg_id, queued_id, done_id)
            succeeded += 1
        except Exception as e:
            print(f"  failed to process {msg_id}: {e}")
            try:
                relabel_message(service, msg_id, queued_id, failed_id)
            except Exception as relabel_err:
                print(f"  also failed to relabel: {relabel_err}")
            failed += 1

    print(f"done — {succeeded} processed, {failed} failed")
def _process_one(
    service,
    msg_id: str,
    queued_label_id: str,
    done_label_id: str,
) -> None:
    """Process a single message: fetch, parse, save folder, write envelope, relabel.

    All artifacts for this message land in ONE folder:
        inbox/pending/<envelope_id>/
            ├── envelope.json
            └── <attachment files...>

    On any failure before the relabel step, raises — the message stays
    queued and will be retried next run. The relabel happens LAST so we
    never lose data on partial failure.
    """
    # 1. Fetch and parse
    raw = fetch_message(service, msg_id)
    parsed = parse_message(raw)

    # 2. Classify
    kind = classify(parsed)

    # 3. Generate envelope ID and create the folder up front
    envelope_id = make_envelope_id(parsed.internal_date)
    envelope_folder = os.path.join(PENDING_DIR, envelope_id)
    os.makedirs(envelope_folder, exist_ok=True)

    # 4. Download attachments directly into the envelope folder
    saved_attachments = []
    for parsed_att in parsed.attachments:
        # Filename is just the original name — folder name disambiguates
        attachment_path = os.path.join(envelope_folder, parsed_att.filename)

        # Atomic write: tmp then rename
        bytes_data = get_attachment_bytes(service, msg_id, parsed_att.attachment_id)
        tmp_path = attachment_path + ".tmp"
        with open(tmp_path, "wb") as f:
            f.write(bytes_data)
        os.rename(tmp_path, attachment_path)

        saved_attachments.append(Attachment(
            filename=parsed_att.filename,
            path=attachment_path,
            mime_type=parsed_att.mime_type,
            size_bytes=parsed_att.size_bytes,
        ))

    # 5. Build the envelope
    envelope = Envelope(
        schema_version=1,
        id=envelope_id,
        received_at=datetime.now(timezone.utc),
        kind=kind,
        source="gmail",
        source_metadata={
            "gmail_message_id": parsed.gmail_message_id,
            "gmail_thread_id": parsed.gmail_thread_id,
            "from": parsed.from_address,
            "subject": parsed.subject,
            "internal_date": parsed.internal_date.isoformat(),
        },
        body_text=parsed.body_text,
        attachments=saved_attachments,
    )

    # 6. Write envelope.json INSIDE the envelope folder (atomic)
    envelope_path = os.path.join(envelope_folder, "envelope.json")
    envelope.write_to(envelope_path)

    # 7. Relabel — must be LAST. If we crashed before this, the message
    # stays queued and gets retried next run.
    relabel_message(service, msg_id, queued_label_id, done_label_id)