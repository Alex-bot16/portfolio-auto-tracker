"""Pipeline orchestrator — the entry point's entry point.

For now (slice 1), this just lists envelopes, summarizes them, and
archives them. No Claude calls, no rendering, no email. The point is
to prove the file-shuffling layer works before adding intelligence.

Future slices will add:
  - Loading philosophy + previous portfolio + context
  - Calling Claude on screenshot envelopes to update the portfolio
  - Calling Claude on reply envelopes to update context
  - Rendering the new portfolio to PDF
  - Sending the PDF via Gmail
  - Then archive.
"""

# Import all modules.
from . import archive, intake


def run() -> None:
    """Run one full pass over inbox/pending/."""

    # Valid envelopes
    envelopes_with_paths = intake.load_pending()

    if not envelopes_with_paths:
        print("no envelopes to process")
        return

    # Tally by kind so the user can see at a glance what we found
    counts = {"screenshot": 0, "reply": 0, "unknown": 0}
    for envelope, _ in envelopes_with_paths:
        counts[envelope.kind.value] += 1

    print(f"found {len(envelopes_with_paths)} envelope(s)")
    print(f"  screenshots: {counts['screenshot']}")
    print(f"  replies:     {counts['reply']}")
    print(f"  unknown:     {counts['unknown']}")

    # Slice 1: just archive everything. Real processing comes later.
    succeeded = 0
    failed = 0
    for envelope, path in envelopes_with_paths:
        try:




            
            archive.archive(path)
            print(f"  archived: {envelope.id}")
            succeeded += 1
        except Exception as e:
            print(f"  failed to archive {envelope.id}: {e}")
            failed += 1

    print(f"done — {succeeded} archived, {failed} failed")