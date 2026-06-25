# Create a fake envelope to archive
mkdir -p inbox/pending
echo '{"test": "data"}' > inbox/pending/test_archive.json

# Try archiving it
python -c "from pipeline.archive import archive; archive('inbox/pending/test_archive.json')"

# Verify
ls inbox/pending/        # should NOT show test_archive.json
ls inbox/processed/      # should show test_archive.json