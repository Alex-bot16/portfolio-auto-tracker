# receiver/config.py
"""Configuration for the Gmail receiver.

For Gmail-side setup (labels, filters), see SETUP.md in the project root.
The constants below must match the labels and filter rules created there.
"""

# === Gmail labels ===
# Created manually in Gmail. See SETUP.md.
QUEUED_LABEL = "portfolio/queued"
DONE_LABEL = "portfolio/done"
FAILED_LABEL = "portfolio/failed"

# The Gmail filter should match emails where:
#   From: ALLOWED_SENDER
#   To:   FORWARD_ADDRESS
# and apply the label QUEUED_LABEL.
ALLOWED_SENDER = "alexandre.bommensath@gmail.com"
FORWARD_ADDRESS = "bommensathalexandre@gmail.com"

# === Filesystem paths ===
PENDING_DIR = "inbox/pending"
BLOBS_DIR = "inbox/blobs"