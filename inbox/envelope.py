"""
Envelope schema — the contract between the receiver and the pipeline.


WHAT THIS MODULE IS
───────────────────

This module defines the data format used to pass information from the
receiver (which talks to Gmail) to the pipeline (which talks to Claude).
It is the *contract* between them. Neither half talks to the other
directly — they only meet through Envelope files written to disk.

Three things live here:

  - EnvelopeKind     enum: SCREENSHOT, REPLY, UNKNOWN
  - Attachment       dataclass: one saved attachment file on disk
  - Envelope         dataclass: the full record of one inbound email,
                     with serialization to and from JSON

This module imports nothing from the receiver and nothing from the
pipeline. It is deliberately neutral. Both sides depend on it; it
depends on neither.


WHY A SHARED CONTRACT
─────────────────────

The receiver and pipeline are independent programs that run at
different times. The receiver runs every 15 minutes, fetches new
mail, and writes Envelope files to inbox/pending/. The pipeline runs
once a week, reads those files, calls Claude, and produces digests.

Because they run independently, they cannot share Python objects in
memory. They communicate by *writing files*. JSON is the wire format
that survives the gap between processes.

If the receiver and pipeline each defined their own envelope shape,
they would silently drift — one side adds a field, the other never
notices, the system breaks at the seam without anyone realizing.
By defining the format ONCE in this module and importing from both
sides, drift becomes impossible. If a field changes, both halves see
it via the same dataclass.


HOW THE CONTRACT WORKS
──────────────────────

The receiver builds Envelope objects in Python:

    envelope = Envelope(
        schema_version=1,
        id=make_envelope_id(datetime.now(timezone.utc)),
        received_at=datetime.now(timezone.utc),
        kind=EnvelopeKind.SCREENSHOT,
        source="gmail",
        source_metadata={"gmail_message_id": "...", "from": "...", ...},
        body_text="...",
        attachments=[Attachment(filename=..., path=..., ...), ...],
    )

It then serializes them to JSON and writes them atomically:

    envelope.write_to("inbox/pending/<id>.json")

The pipeline later reads the same files:

    with open(path) as f:
        envelope = Envelope.from_json(f.read())

    if envelope.kind == EnvelopeKind.SCREENSHOT:
        ...

Both halves work with typed Envelope objects in Python. JSON is just
the format the data takes while it's at rest on disk.


THE FIELDS
──────────

Every Envelope has eight fields:

  schema_version    int.   The version of this format. Currently 1.
                           If the format ever changes, bump this and
                           teach from_json() how to migrate old files.

  id                str.   Globally unique, sortable by time.
                           Used as the envelope's filename:
                           inbox/pending/<id>.json

  received_at       datetime (UTC).  When the receiver finished
                           processing this email and wrote it to disk.

  kind              EnvelopeKind enum.  How the receiver classified
                           the email's shape — see classifier.py:
                             SCREENSHOT  → has visual attachments
                             REPLY       → reply to a previous digest
                             UNKNOWN     → neither; pipeline skips

  source            str.   Which receiver produced this envelope.
                           Currently always "gmail". When/if a Drive
                           receiver is added, this becomes "drive".
                           The pipeline can branch on this if needed.

  source_metadata   dict.  Receiver-specific metadata. Opaque to the
                           pipeline. For Gmail, contains gmail_message_id,
                           from address, subject, etc. The pipeline
                           shouldn't read from here — those concerns
                           are upstream of analysis.

  body_text         str.   The email's plain-text body, with HTML
                           stripped if needed. Always a string —
                           empty when the email had no body content.

  attachments       list[Attachment].  Zero or more saved attachments.
                           Each one points at a binary file on disk
                           (the path field) — the bytes themselves are
                           not in the envelope.


THE LAYERED PHILOSOPHY
──────────────────────

This module sits at the bottom of a deliberate three-layer design:

      Receiver (Gmail-flavoured)
                   │  produces Envelope files
                   ▼
      Envelope (this module)              ← shared contract
                   ▲
                   │  consumes Envelope files
      Pipeline (Claude-flavoured)

Both layers above import from this one. This layer imports nothing
upward.

That direction matters. It means swapping a receiver (Gmail → Drive)
or swapping the analysis (Claude → another LLM) requires no change to
this module. The contract is stable; the implementations on either
side can evolve independently.


SCHEMA EVOLUTION
────────────────

If the schema needs to change in the future:

  - Adding a NEW field with a default: safe. Old envelopes still
    parse; new envelopes have the new field.

  - Renaming or removing a field: NOT safe. Bump schema_version,
    update from_json() to handle both versions, migrate or rewrite
    old envelopes if needed.

In practice this should be rare. The schema is small and the fields
are general enough to last.
"""


import json
import os
import secrets
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from enum import Enum

class EnvelopeKind(Enum):
    SCREENSHOT = "screenshot"
    REPLY = "reply"
    UNKNOWN = "unknown"

@dataclass
class Attachment:
    """One attachment, saved to disk by the receiver."""
    filename: str       # original filename from the email (e.g. "revolut.jpeg")
    path: str           # where it lives on disk (e.g. "inbox/blobs/2026...__revolut.jpeg")
    mime_type: str      # e.g. "image/jpeg" or "application/pdf"
    size_bytes: int     # for sanity checks

def make_envelope_id(when: datetime) -> str:
    """Make a sortable, unique envelope ID from a timestamp.

    Format: "2026-05-07T08-12-33__a3f9c1"

    The timestamp prefix means filenames sort chronologically when listed.
    The random suffix prevents collisions if two emails arrive in the same
    second.

    Note the dashes (not colons) between hours/minutes/seconds — colons
    aren't allowed in filenames on some systems.
    """
    timestamp = when.strftime("%Y-%m-%dT%H-%M-%S")
    suffix = secrets.token_hex(3)   # 6 hex chars
    return f"{timestamp}__{suffix}"


@dataclass
class Envelope:
    """The receiver's record of one inbound email.

    Written to inbox/pending/<id>.json after the receiver processes a message.
    The pipeline reads these and acts on them.
    """
    schema_version: int
    id: str
    received_at: datetime
    kind: EnvelopeKind
    source: str                          # "gmail" | "drive" | "manual"
    source_metadata: dict                # opaque to pipeline; receiver-specific
    body_text: str
    attachments: list[Attachment] = field(default_factory=list)

    def to_json(self) -> str:
        """Serialize to a JSON string."""
        data = {
            "schema_version": self.schema_version,
            "id": self.id,
            "received_at": self.received_at.isoformat(),
            "kind": self.kind.value,                          # enum → string
            "source": self.source,
            "source_metadata": self.source_metadata,
            "body_text": self.body_text,
            "attachments": [asdict(a) for a in self.attachments],
        }
        return json.dumps(data, indent=2)

    @classmethod
    def from_json(cls, raw: str) -> "Envelope":
        """Parse a JSON string into an Envelope object."""
        data = json.loads(raw)
        return cls(
            schema_version=data["schema_version"],
            id=data["id"],
            received_at=datetime.fromisoformat(data["received_at"]),
            kind=EnvelopeKind(data["kind"]),                  # string → enum
            source=data["source"],
            source_metadata=data["source_metadata"],
            body_text=data["body_text"],
            attachments=[Attachment(**a) for a in data["attachments"]],
        )

    def write_to(self, path: str) -> None:
        """Write the envelope to disk atomically.

        Writes to <path>.tmp first, then renames to <path>. This prevents
        the pipeline from reading a half-written file if it happens to scan
        the directory while we're writing.
        """
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp_path = path + ".tmp"
        with open(tmp_path, "w") as f:
            f.write(self.to_json())
        os.rename(tmp_path, path)