.PHONY: help receive pipeline test test-claude test-analysis clean-state clean-cache clean-all

help:  ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-18s %s\n", $$1, $$2}'

# ─── Running the system ──────────────────────────────────────────────

receive:  ## Process queued Gmail messages → envelopes on disk
	python -m receiver

pipeline:  ## Process pending envelopes → portfolio PDF
	python -m pipeline

# ─── Tests ───────────────────────────────────────────────────────────

test:  ## Run the full test suite (auth, parser, classifier, etc.)
	python tests/test_all.py

test-claude:  ## Smoke test: verify Claude API works
	python tests/test_claude.py

test-analysis:  ## Smoke test: full analysis on a pending envelope
	python tests/test_analysis.py

# ─── Cleanup ─────────────────────────────────────────────────────────

clean-state:  ## Wipe inbox queue and generated outputs
	@rm -rf inbox/blobs 2>/dev/null || true
	@find inbox/pending -mindepth 1 -delete 2>/dev/null || true
	@find inbox/processed -mindepth 1 -delete 2>/dev/null || true
	@find state/outputs/history -mindepth 1 -delete 2>/dev/null || true
	@rm -rf state/outputs/current 2>/dev/null || true
	@echo "✓ inbox + state cleared"

clean-cache:  ## Remove __pycache__ folders
	@find . -type d -name __pycache__ -not -path './.venv/*' -exec rm -rf {} + 2>/dev/null || true
	@echo "✓ pycache cleared"

clean-all: clean-state clean-cache  ## Run all cleanups
	@echo "✓ everything clean"