.PHONY: help accept-pdf digest send full-digest digest-dry digest-fast research research-brief research-macro prices extract test test-online clean-state clean-cache clean-all

help:  ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-16s %s\n", $$1, $$2}'

# ─── Running the system ──────────────────────────────────────────────

accept-pdf:  ## Promote newest inbox PDF AND extract it into profile.json (one Claude call)
	python -c "from pipeline import accept_pdf; accept_pdf()"

digest:  ## Build a run from profile (PDF + research), save it — does NOT send
	python main.py

send:  ## Send the latest saved run by email. Override recipient: make send TO=a@x.com
	python -c "from pipeline import send_run; send_run(to=('$(TO)' or None))"

full-digest:  ## Build a run AND send it. Override recipient: make full-digest TO=a@x.com
	python -c "from pipeline import run_digest; run_digest(send_email=True, to=('$(TO)' or None))"

digest-dry:  ## Run from profile WITHOUT research or PDF render (fast wiring check)
	python -c "from pipeline import run_digest; run_digest(do_research=False, render_pdf=False)"

digest-fast:  ## Full run but research only 2 conviction names (RESEARCH_LIMIT=2)
	python -c "import config; config.RESEARCH_LIMIT=2; from pipeline import run_digest; run_digest()"

# ─── Sandbox (iterate on one piece) ──────────────────────────────────

extract:  ## Preview PDF -> profile extraction (does NOT save profile.json)
	python -m sandbox.try_extract

prices:  ## Price every ticker in the saved profile (bypasses cache)
	python -m sandbox.try_prices

research:  ## Deep research one ticker:  make research T=OKLO
	python -m sandbox.try_research $(T)

research-brief:  ## Brief one-liner for one ticker:  make research-brief T=OKLO
	python -m sandbox.try_research $(T) --brief

research-macro:  ## Macro briefing:  make research-macro T="VUAA WEXE"
	python -m sandbox.try_research --macro $(T)

# ─── Tests ───────────────────────────────────────────────────────────

test:  ## Offline unit tests (no API key, no network)
	python -m tests.test_all

test-online:  ## Smoke test: verify the Claude API key works
	python -m tests.test_online

# ─── Cleanup ─────────────────────────────────────────────────────────

clean-state:  ## Wipe inbox, current PDF, profile, cache, and outputs
	@rm -rf portfolio_inbox/* 2>/dev/null || true
	@rm -rf state/current/* 2>/dev/null || true
	@rm -rf state/portfolios/* 2>/dev/null || true
	@rm -f state/profile.json state/price_cache.json 2>/dev/null || true
	@find state/outputs/history -mindepth 1 -delete 2>/dev/null || true
	@echo "state cleared"

clean-cache:  ## Remove the price cache only
	@rm -f state/price_cache.json 2>/dev/null || true
	@echo "price cache cleared"

clean-pycache:  ## Remove __pycache__ folders
	@find . -type d -name __pycache__ -not -path './.venv/*' -exec rm -rf {} + 2>/dev/null || true
	@echo "pycache cleared"

clean-all: clean-state clean-pycache  ## State + pycache
	@echo "all clean"
