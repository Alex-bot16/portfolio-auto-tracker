"""Archive: move processed envelopes out of inbox/pending/.

After the pipeline successfully processes an envelope, this module
moves the envelope's folder from inbox/pending/ to inbox/processed/.

The folder contains envelope.json plus any attachments. The whole
folder moves as one unit — JSON and attachments stay together.
"""

import os
import shutil

from inbox.config import PROCESSED_DIR


def archive(envelope_folder: str) -> None:
    """Move an envelope folder from inbox/pending/ to inbox/processed/.

    Creates inbox/processed/ if it doesn't exist. The destination folder
    name matches the source folder name — envelope IDs are unique by
    construction, so collisions shouldn't happen.

    Raises whatever shutil.move raises on failure (permission, disk
    full, etc.). The orchestrator handles it.
    """
    os.makedirs(PROCESSED_DIR, exist_ok=True)

    folder_name = os.path.basename(envelope_folder.rstrip(os.sep))
    destination = os.path.join(PROCESSED_DIR, folder_name)

    shutil.move(envelope_folder, destination)