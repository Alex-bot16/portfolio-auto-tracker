"""Intake: read all valid envelopes from inbox/pending/.

The pipeline's first stage. Loads every envelope it can parse and returns
them as (envelope, folder_path) pairs so the orchestrator can act on the
envelope and later move the whole folder via archive().

Each envelope lives in its own subfolder under inbox/pending/:

    inbox/pending/<envelope_id>/
        ├── envelope.json
        └── <attachment files...>

Subfolders without an envelope.json are skipped silently.
Folders that fail to parse — corrupted JSON, schema mismatch — are
skipped with a printed warning. One bad envelope shouldn't prevent
the others from being processed.

UNKNOWN envelopes are NOT filtered here — that's a policy decision the
orchestrator makes. Intake's job is to load; the orchestrator decides
what to do with each kind.
"""

import os

from inbox.config import PENDING_DIR
from inbox.envelope import Envelope


def load_pending() -> list[tuple[Envelope, str]]:
    """Return all valid envelopes in inbox/pending/, paired with their folders.

    Returns a list of (envelope, folder_path) tuples. The folder_path is
    the path to the envelope's directory (e.g. "inbox/pending/<id>/"),
    NOT to the envelope.json file. Pass this folder_path to archive() or
    storage functions that need to operate on the whole envelope.

    Sorted by folder name (envelope IDs start with timestamps, so this
    is chronological — oldest first).
    """
    if not os.path.exists(PENDING_DIR):
        return []

    envelopes: list[tuple[Envelope, str]] = []

    for entry in sorted(os.listdir(PENDING_DIR)):
        folder = os.path.join(PENDING_DIR, entry)

        # Skip files (only consider directories)
        if not os.path.isdir(folder):
            continue

        envelope_json = os.path.join(folder, "envelope.json")
        if not os.path.exists(envelope_json):
            continue  # not an envelope folder — silently skip

        try:
            with open(envelope_json, "r") as f:
                envelope = Envelope.from_json(f.read())
        except Exception as e:
            print(f"  skipping {folder}: {type(e).__name__}: {e}")
            continue

        envelopes.append((envelope, folder))

    return envelopes